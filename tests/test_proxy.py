"""Tests for the proxy parser — every format a real provider has shipped."""

from __future__ import annotations

import pytest

from funbrowser.proxy import Proxy, ProxyParseError
from funbrowser.proxy import parse as parse_proxy


def test_plain_host_port_no_auth() -> None:
    p = parse_proxy("1.2.3.4:8080")
    assert p == Proxy("http", "1.2.3.4", 8080)
    assert p.chrome_arg() == "http://1.2.3.4:8080"


def test_hostname_host_port() -> None:
    p = parse_proxy("proxy.example.com:3128")
    assert p == Proxy("http", "proxy.example.com", 3128)


def test_scheme_then_host_port() -> None:
    p = parse_proxy("socks5://1.2.3.4:1080")
    assert p == Proxy("socks5", "1.2.3.4", 1080)
    assert p.is_socks


def test_standard_url_with_auth() -> None:
    p = parse_proxy("http://alice:secret@1.2.3.4:8080")
    assert p == Proxy("http", "1.2.3.4", 8080, "alice", "secret")
    assert p.has_auth


def test_https_url_with_auth() -> None:
    p = parse_proxy("https://alice:secret@proxy.example.com:443")
    assert p.scheme == "https"
    assert p.host == "proxy.example.com"
    assert p.port == 443


def test_implicit_scheme_with_at_auth() -> None:
    p = parse_proxy("alice:secret@1.2.3.4:8080")
    assert p == Proxy("http", "1.2.3.4", 8080, "alice", "secret")


def test_host_port_then_user_pass_via_at() -> None:
    # Some providers ship `host:port@user:pass`.
    p = parse_proxy("1.2.3.4:8080@alice:secret")
    assert p == Proxy("http", "1.2.3.4", 8080, "alice", "secret")


def test_host_port_user_pass_colon_separated() -> None:
    p = parse_proxy("1.2.3.4:8080:alice:secret")
    assert p == Proxy("http", "1.2.3.4", 8080, "alice", "secret")


def test_user_pass_host_port_colon_separated() -> None:
    p = parse_proxy("alice:secret:1.2.3.4:8080")
    assert p == Proxy("http", "1.2.3.4", 8080, "alice", "secret")


def test_host_port_user_no_password() -> None:
    p = parse_proxy("1.2.3.4:8080:alice")
    assert p == Proxy("http", "1.2.3.4", 8080, "alice")
    assert p.has_auth
    assert p.password is None


def test_socks5h_passthrough() -> None:
    p = parse_proxy("socks5h://alice:secret@1.2.3.4:1080")
    assert p.scheme == "socks5h"
    # chrome_arg normalises to socks5 since Chrome doesn't speak socks5h
    assert p.chrome_arg() == "socks5://1.2.3.4:1080"


def test_password_can_contain_colons() -> None:
    # The standard URL form supports it via user:pass@host:port where pass
    # may contain ':' — we split user:pass at the FIRST colon in the auth
    # part. So "a:b:c@h:1" -> user=a pass="b:c".
    p = parse_proxy("alice:p:a:s:s@1.2.3.4:8080")
    assert p.username == "alice"
    assert p.password == "p:a:s:s"
    assert p.host == "1.2.3.4"
    assert p.port == 8080


def test_idempotent_on_proxy_input() -> None:
    p = Proxy("http", "1.2.3.4", 8080, "u", "p")
    assert parse_proxy(p) is p


def test_uppercase_scheme_normalised() -> None:
    assert parse_proxy("HTTP://1.2.3.4:8080").scheme == "http"
    assert parse_proxy("SOCKS5://1.2.3.4:1080").scheme == "socks5"


def test_whitespace_trimmed() -> None:
    p = parse_proxy("  1.2.3.4:8080  ")
    assert p.host == "1.2.3.4"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "    ",
        "not-a-proxy",
        "1.2.3.4",  # no port
        "1.2.3.4:",  # empty port
        ":8080",  # no host
        "1.2.3.4:99999",  # port out of range
        "1.2.3.4:0",  # port 0
        "ftp://1.2.3.4:8080",  # unknown scheme
        "@1.2.3.4:8080",  # empty user
        "alice@:8080",  # empty host
        "alice:p:1.2.3.4",  # 3 segs, second not a port
    ],
)
def test_invalid_proxies_raise(bad: str) -> None:
    with pytest.raises(ProxyParseError):
        parse_proxy(bad)


def test_url_round_trip_with_auth() -> None:
    p = parse_proxy("http://alice:secret@1.2.3.4:8080")
    assert p.url() == "http://alice:secret@1.2.3.4:8080"


def test_url_round_trip_without_auth() -> None:
    p = parse_proxy("1.2.3.4:8080")
    assert p.url() == "http://1.2.3.4:8080"


def test_chrome_arg_excludes_auth() -> None:
    p = parse_proxy("http://alice:secret@1.2.3.4:8080")
    assert "alice" not in p.chrome_arg()
    assert "secret" not in p.chrome_arg()


def test_localhost_recognised_as_host() -> None:
    p = parse_proxy("localhost:8080:user:pass")
    assert p.host == "localhost"
    assert p.port == 8080
    assert p.username == "user"


def test_user_pass_with_numeric_username() -> None:
    # Provider sometimes uses customer-id as username.
    p = parse_proxy("12345:secret:1.2.3.4:8080")
    assert p.username == "12345"
    assert p.password == "secret"
    assert p.host == "1.2.3.4"
