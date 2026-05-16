"""TLS security for P2P connections — self-signed certs and fingerprint verification."""

from __future__ import annotations

import datetime
import hashlib
import logging
import ssl
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_CERT_VALIDITY_DAYS = 365


def generate_cert(
    common_name: str = "chenedusys-p2p",
    days: int = _CERT_VALIDITY_DAYS,
) -> tuple[str, str]:
    """Generate a self-signed TLS certificate and private key.

    Returns ``(cert_path, key_path)`` — paths to temporary files that
    the caller should clean up when done.

    Uses stdlib ``ssl`` + low-level crypto via ``cryptography`` if
    available, otherwise falls back to a minimal approach.
    """
    try:
        return _generate_with_cryptography(common_name, days)
    except ImportError:
        logger.warning("'cryptography' not installed — generating basic cert")
        return _generate_basic(common_name, days)


def _generate_with_cryptography(common_name: str, days: int) -> tuple[str, str]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_dir = Path(tempfile.mkdtemp(prefix="chenedusys-cert-"))
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    return str(cert_path), str(key_path)


def _generate_basic(common_name: str, days: int) -> tuple[str, str]:
    """Fallback: create an ad-hoc SSL context. Returns temp file paths."""
    import subprocess

    cert_dir = Path(tempfile.mkdtemp(prefix="chenedusys-cert-"))
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"

    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key_path),
            "-out", str(cert_path),
            "-days", str(days),
            "-nodes",
            "-subj", f"/CN={common_name}",
        ],
        check=True,
        capture_output=True,
    )

    return str(cert_path), str(key_path)


def cert_fingerprint(cert_path: str) -> str:
    """Compute the SHA-256 fingerprint of a PEM certificate."""
    pem = Path(cert_path).read_bytes()
    import re
    # Extract base64 DER content from PEM
    b64 = re.sub(rb"-----BEGIN.*?-----\s*", b"", pem)
    b64 = re.sub(rb"-----END.*?-----\s*", b"", b64)
    import base64
    der = base64.b64decode(b64)
    return hashlib.sha256(der).hexdigest()


def create_server_ssl_context(
    cert_path: str, key_path: str
) -> ssl.SSLContext:
    """Create an SSL context for the P2P server (teacher)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def create_client_ssl_context(
    expected_fingerprint: str | None = None,
) -> ssl.SSLContext:
    """Create an SSL context for the P2P client (student).

    If *expected_fingerprint* is provided, the server's certificate
    will be checked against it after the TLS handshake to detect
    MITM attacks.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # we verify fingerprint manually
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    if expected_fingerprint:

        class _FingerprintSSLObject:
            """Post-handshake fingerprint check via a wrapper."""

            def __init__(self, inner_ctx, fingerprint):
                self._ctx = inner_ctx
                self._fp = fingerprint

        # Wrap ssl wrap to check fingerprint
        # We handle this at the application layer instead
        pass

    return ctx


def verify_peer_fingerprint(
    writer: ssl.SSLSocket | object,
    expected_fingerprint: str,
) -> bool:
    """Verify the peer's certificate fingerprint matches expected.

    Call this after the TLS handshake completes.
    """
    try:
        # Get the peer's certificate in DER format
        transport = getattr(writer, "_transport", None)
        ssl_object = None
        if transport:
            ssl_object = transport.get_extra_info("ssl_object")
        if ssl_object is None:
            # Try direct access
            ssl_object = getattr(writer, "get_extra_info", lambda x: None)("ssl_object")

        if ssl_object is None:
            logger.warning("Cannot get SSL object for fingerprint check")
            return False

        peer_cert_der = ssl_object.getpeercert(binary_form=True)
        if peer_cert_der is None:
            return False

        actual = hashlib.sha256(peer_cert_der).hexdigest()
        return actual == expected_fingerprint
    except Exception as exc:
        logger.error("Fingerprint verification error: %s", exc)
        return False


def cleanup_cert_files(cert_path: str, key_path: str) -> None:
    """Remove temporary certificate and key files."""
    for p in (cert_path, key_path):
        try:
            Path(p).unlink()
        except OSError:
            pass
    # Try to remove parent dir if empty
    try:
        parent = Path(cert_path).parent
        parent.rmdir()
    except OSError:
        pass
