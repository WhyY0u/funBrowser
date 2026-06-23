"""Local MITM proxy: terminate Chrome's TLS, re-encrypt upstream via curl_cffi.

**Status: alpha**. The architecture is here and the CA / cert minting works
end-to-end, but the proxy loop currently handles only basic HTTP/1.1
through the CONNECT tunnel. WebSocket upgrades, HTTP/2, and CONNECT-tunnel
keep-alive across multiple requests are TODO.

Why it exists: Chrome's outgoing TLS handshake produces a known
JA3/JA4 that some antibots fingerprint. By terminating TLS at the proxy
and re-encrypting upstream with ``curl_cffi``'s spoofed TLS, we replace
Chrome's signature with a configurable one (chrome131, safari17_0, etc.).

How it's used::

    async with await funbrowser.start(tls_impersonate="chrome131") as browser:
        # Chrome auto-routes through 127.0.0.1:<port> with the CA trusted.
        tab = await browser.get("https://target.com")

The wiring lives in :class:`funbrowser.Browser`. This file is the
transport layer.

For full Chrome-traffic TLS spoofing including all HTTP/2 + WebSocket
edge cases, M10b sizes at roughly **3-5 days of focused work** by an
engineer familiar with mitmproxy internals. The current implementation
is sized for "works on simple GET/POST against typical APIs".
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import tempfile
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from .ca import CABundle, ensure_root_ca, mint_leaf

try:
    from curl_cffi import requests as _cf
except ImportError:  # pragma: no cover
    _cf = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class MitmProxy:
    """A localhost HTTPS-intercepting proxy that re-encrypts via curl_cffi.

    Lifecycle::

        proxy = MitmProxy(impersonate="chrome131")
        await proxy.start()
        # browser uses proxy.url + proxy.spki_for_chrome
        await proxy.stop()

    Or as ``async with``. Multiple proxies on different ports are fine —
    each pool browser can have its own.
    """

    def __init__(
        self,
        *,
        impersonate: str = "chrome131",
        host: str = "127.0.0.1",
        port: int = 0,
        ca_dir: Path | str | None = None,
    ) -> None:
        if _cf is None:
            raise ImportError(
                "MitmProxy requires `pip install funbrowser[tls]` (adds curl_cffi + cryptography)."
            )
        self._impersonate = impersonate
        self._host = host
        self._port = port
        self._ca_dir = Path(ca_dir) if ca_dir else Path(tempfile.mkdtemp(prefix="funbrowser-ca-"))
        self._ca: CABundle = ensure_root_ca(self._ca_dir)
        self._server: asyncio.base_events.Server | None = None
        self._leaf_cache: dict[str, tuple[bytes, bytes]] = {}
        self._http: Any = None

    @property
    def url(self) -> str:
        assert self._port > 0, "call start() first"
        return f"http://{self._host}:{self._port}"

    @property
    def spki_for_chrome(self) -> str:
        """Base64 SPKI for ``--ignore-certificate-errors-spki-list=<spki>``."""
        return self._ca.spki_b64

    @property
    def chrome_arg(self) -> str:
        return f"--ignore-certificate-errors-spki-list={self._ca.spki_b64}"

    async def start(self) -> None:
        self._http = _cf.AsyncSession(impersonate=self._impersonate)  # type: ignore[arg-type]
        self._server = await asyncio.start_server(self._on_client, host=self._host, port=self._port)
        sock = next(iter(self._server.sockets or []), None)
        if sock is not None:
            self._port = int(sock.getsockname()[1])

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._http is not None:
            await self._http.close()
            self._http = None

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.stop()

    # ── proxy loop ────────────────────────────────────────────────────

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """One incoming Chrome connection.

        Chrome's HTTP proxy contract:
        - For plain HTTP: forwards the full request as-is.
        - For HTTPS: sends ``CONNECT host:port HTTP/1.1`` first. We
          terminate TLS in-process and serve requests on the tunnel.
        """
        try:
            line = await reader.readline()
            if not line:
                return
            request = line.decode("iso-8859-1", errors="replace").strip()
            # Read remaining headers to flush them off the wire.
            while True:
                header = await reader.readline()
                if header == b"\r\n" or not header:
                    break

            method, target, _proto = request.split(" ", 2)
            if method.upper() == "CONNECT":
                host, _, port_str = target.partition(":")
                port = int(port_str or "443")
                await self._tunnel_https(reader, writer, host, port)
            else:
                # Plain HTTP — proxy directly. Out of scope for stealth (HTTP
                # has no TLS to spoof). Best-effort fallback.
                await self._proxy_plain(reader, writer, method, target)
        except Exception:
            logger.exception("mitm: client handler crashed")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _tunnel_https(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        host: str,
        port: int,
    ) -> None:
        # Hand Chrome a 200 so it starts the inner TLS handshake.
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()

        leaf = self._leaf_cache.get(host)
        if leaf is None:
            leaf = mint_leaf(self._ca, host)
            self._leaf_cache[host] = leaf
        cert_pem, key_pem = leaf

        # Build an SSLContext from the in-memory leaf cert.
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        with (
            tempfile.NamedTemporaryFile(delete=False, suffix=".crt") as cf,
            tempfile.NamedTemporaryFile(delete=False, suffix=".key") as kf,
        ):
            cf.write(cert_pem)
            kf.write(key_pem)
            cert_path, key_path = cf.name, kf.name
        try:
            ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
        finally:
            Path(cert_path).unlink(missing_ok=True)
            Path(key_path).unlink(missing_ok=True)

        loop = asyncio.get_running_loop()
        transport = writer.transport
        proto = transport.get_protocol()
        try:
            new_transport = await loop.start_tls(
                transport,
                proto,
                ctx,
                server_side=True,
            )
        except Exception:
            logger.exception("mitm: TLS upgrade failed for %s:%s", host, port)
            return

        # New reader/writer over the wrapped transport. We re-use proto's
        # buffers — for production use, build dedicated streams. Alpha.
        inner_writer: asyncio.StreamWriter = writer
        inner_writer._transport = new_transport  # type: ignore[attr-defined]
        try:
            await self._serve_https_inner(reader, inner_writer, host, port)
        except Exception:
            logger.exception("mitm: inner HTTPS serve crashed for %s:%s", host, port)

    async def _serve_https_inner(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        host: str,
        port: int,
    ) -> None:
        """Read one HTTP/1.1 request inside the TLS tunnel, forward via curl_cffi.

        Real browsers reuse the tunnel for keep-alive; we honour one
        request per CONNECT in this alpha. The browser will reconnect for
        subsequent fetches.
        """
        line = await reader.readline()
        if not line:
            return
        try:
            method, path, _proto = line.decode("iso-8859-1").strip().split(" ", 2)
        except ValueError:
            return

        headers: list[tuple[str, str]] = []
        while True:
            h = await reader.readline()
            if not h or h == b"\r\n":
                break
            if b":" not in h:
                continue
            k, v = h.decode("iso-8859-1").split(":", 1)
            headers.append((k.strip(), v.strip()))

        body_len = 0
        for k, v in headers:
            if k.lower() == "content-length":
                try:
                    body_len = int(v)
                except ValueError:
                    body_len = 0
        body = b""
        if body_len > 0:
            body = await reader.readexactly(body_len)

        url = f"https://{host}:{port}{path}" if port != 443 else f"https://{host}{path}"
        # Strip hop-by-hop headers; curl_cffi sets its own UA/cipher list.
        hop_by_hop = {
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
        }
        fwd_headers = {k: v for k, v in headers if k.lower() not in hop_by_hop}

        try:
            r = await self._http.request(
                method.upper(),
                url,
                headers=fwd_headers,
                data=body or None,
                allow_redirects=False,
            )
        except Exception as exc:
            logger.warning("mitm: upstream %s %s failed: %s", method, url, exc)
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            return

        status = int(getattr(r, "status_code", 502))
        reason = "OK" if status < 400 else "ERR"
        out = [f"HTTP/1.1 {status} {reason}".encode()]
        # Filter out hop-by-hop on the way back too.
        for k, v in r.headers.items():
            if k.lower() in hop_by_hop:
                continue
            out.append(f"{k}: {v}".encode())
        body_bytes = r.content if isinstance(r.content, bytes) else (r.content or b"")
        out.append(f"Content-Length: {len(body_bytes)}".encode())
        out.append(b"")
        out.append(body_bytes)
        writer.write(b"\r\n".join(out))
        await writer.drain()

    async def _proxy_plain(
        self,
        _reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        method: str,
        target: str,
    ) -> None:
        """Forward a plain-HTTP request through curl_cffi.

        Plain HTTP has no TLS to spoof, but we route it for parity so
        Chrome can use one --proxy-server flag for everything. Headers
        from the original request are dropped in this alpha pass.
        """
        try:
            r = await self._http.request(method.upper(), target, allow_redirects=False)
            writer.write(f"HTTP/1.1 {r.status_code} OK\r\n".encode())
            body = r.content if isinstance(r.content, bytes) else (r.content or b"")
            writer.write(f"Content-Length: {len(body)}\r\n\r\n".encode())
            writer.write(body)
            await writer.drain()
        except Exception:
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
