"""CA cert + leaf cert minting tests (no network)."""

from __future__ import annotations

from pathlib import Path

from cryptography import x509

from funbrowser.tls.ca import ensure_root_ca, mint_leaf


def test_ensure_root_ca_generates_files_on_first_call(tmp_path: Path) -> None:
    ca = ensure_root_ca(tmp_path)
    assert ca.cert_path.exists()
    assert ca.key_path.exists()
    assert ca.cert_pem.startswith(b"-----BEGIN CERTIFICATE-----")
    assert ca.key_pem.startswith(b"-----BEGIN PRIVATE KEY-----")
    assert len(ca.spki_b64) >= 40  # base64-encoded SHA-256 digest


def test_ensure_root_ca_is_idempotent(tmp_path: Path) -> None:
    first = ensure_root_ca(tmp_path)
    second = ensure_root_ca(tmp_path)
    assert first.cert_pem == second.cert_pem
    assert first.key_pem == second.key_pem
    assert first.spki_b64 == second.spki_b64


def test_root_ca_is_marked_as_ca(tmp_path: Path) -> None:
    ca = ensure_root_ca(tmp_path)
    cert = x509.load_pem_x509_certificate(ca.cert_pem)
    bc = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    assert bc.ca is True


def test_mint_leaf_signed_by_ca(tmp_path: Path) -> None:
    ca = ensure_root_ca(tmp_path)
    cert_pem, _key_pem = mint_leaf(ca, "example.com")
    leaf = x509.load_pem_x509_certificate(cert_pem)
    ca_cert = x509.load_pem_x509_certificate(ca.cert_pem)
    assert leaf.issuer == ca_cert.subject
    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "example.com" in san.get_values_for_type(x509.DNSName)


def test_mint_leaf_not_marked_ca(tmp_path: Path) -> None:
    ca = ensure_root_ca(tmp_path)
    cert_pem, _ = mint_leaf(ca, "example.com")
    leaf = x509.load_pem_x509_certificate(cert_pem)
    bc = leaf.extensions.get_extension_for_class(x509.BasicConstraints).value
    assert bc.ca is False
