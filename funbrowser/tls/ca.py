"""Root CA generation + on-the-fly leaf cert minting for the mitm proxy.

The proxy intercepts Chrome's HTTPS by terminating TLS with a leaf cert
that Chrome trusts because the leaf is signed by our root CA. The root
CA is generated once per profile, persisted in the user-data-dir, and
trusted by Chrome via ``--ignore-certificate-errors-spki-list=<spki>``.

Limitations:
- The SPKI-allowlist flag bypasses cert checking for our CA only; it's
  the cleanest way to add trust without OS-level keychain modification.
- Leaf certs are cached in-memory per (host, port) for the proxy's
  lifetime; restarting the proxy regenerates them.
"""

from __future__ import annotations

import base64
import datetime as _dt
import hashlib
from dataclasses import dataclass
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
except ImportError:  # pragma: no cover
    x509 = None  # type: ignore[assignment]


@dataclass(frozen=True)
class CABundle:
    """A root CA: private key + certificate + base64 SPKI hash for Chrome."""

    key_pem: bytes
    cert_pem: bytes
    spki_b64: str
    cert_path: Path
    key_path: Path


def _require_crypto() -> None:
    if x509 is None:
        raise ImportError(
            "funbrowser.tls.ca requires `pip install funbrowser[tls]` (adds cryptography)."
        )


def ensure_root_ca(dir_path: Path | str, *, common_name: str = "FunBrowser MITM Root") -> CABundle:
    """Load (or first-time generate) a root CA in ``dir_path``.

    Returns a :class:`CABundle` with both the PEM bytes (for downstream
    cert minting) and a base64 SPKI digest for Chrome's
    ``--ignore-certificate-errors-spki-list`` flag.
    """
    _require_crypto()
    dir_p = Path(dir_path)
    dir_p.mkdir(parents=True, exist_ok=True)
    cert_p = dir_p / "funbrowser-ca.crt"
    key_p = dir_p / "funbrowser-ca.key"

    if cert_p.exists() and key_p.exists():
        cert_pem = cert_p.read_bytes()
        key_pem = key_p.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_pem)
        return CABundle(
            key_pem=key_pem,
            cert_pem=cert_pem,
            spki_b64=_spki_b64(cert),
            cert_path=cert_p,
            key_path=key_p,
        )

    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    now = _dt.datetime.now(_dt.UTC)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "FunBrowser"),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(days=1))
        .not_valid_after(now + _dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_p.write_bytes(cert_pem)
    key_p.write_bytes(key_pem)

    return CABundle(
        key_pem=key_pem,
        cert_pem=cert_pem,
        spki_b64=_spki_b64(cert),
        cert_path=cert_p,
        key_path=key_p,
    )


def mint_leaf(
    ca: CABundle,
    host: str,
) -> tuple[bytes, bytes]:
    """Mint a per-host leaf cert signed by ``ca``. Returns ``(cert_pem, key_pem)``."""
    _require_crypto()
    ca_cert = x509.load_pem_x509_certificate(ca.cert_pem)
    ca_key = serialization.load_pem_private_key(ca.key_pem, password=None)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = _dt.datetime.now(_dt.UTC)
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, host),
        ]
    )
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(minutes=5))
        .not_valid_after(now + _dt.timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(host)]),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
    )
    leaf_cert = builder.sign(ca_key, hashes.SHA256())  # type: ignore[arg-type]
    return (
        leaf_cert.public_bytes(serialization.Encoding.PEM),
        leaf_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )


def _spki_b64(cert: object) -> str:
    """Compute Chrome's expected ``--ignore-certificate-errors-spki-list`` value."""
    pub_key_bytes = cert.public_key().public_bytes(  # type: ignore[attr-defined]
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashlib.sha256(pub_key_bytes).digest()
    return base64.b64encode(digest).decode("ascii")
