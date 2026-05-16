"""Unit tests for TLS security (cert generation + fingerprint)."""

from __future__ import annotations

import ssl
from pathlib import Path

from chenedusys.transport.security import (
    cert_fingerprint,
    cleanup_cert_files,
    create_client_ssl_context,
    create_server_ssl_context,
    generate_cert,
)


class TestCertGeneration:

    def test_generate_returns_paths(self):
        cert_path, key_path = generate_cert()
        assert Path(cert_path).exists()
        assert Path(key_path).exists()
        cleanup_cert_files(cert_path, key_path)

    def test_generate_cert_readable(self):
        cert_path, key_path = generate_cert()
        cert_text = Path(cert_path).read_text()
        assert "BEGIN CERTIFICATE" in cert_text
        key_text = Path(key_path).read_text()
        assert "BEGIN" in key_text
        cleanup_cert_files(cert_path, key_path)

    def test_generate_custom_cn(self):
        cert_path, key_path = generate_cert(common_name="test-meeting-123")
        cert_text = Path(cert_path).read_text()
        assert "BEGIN CERTIFICATE" in cert_text
        cleanup_cert_files(cert_path, key_path)


class TestFingerprint:

    def test_fingerprint_is_hex(self):
        cert_path, key_path = generate_cert()
        fp = cert_fingerprint(cert_path)
        assert len(fp) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in fp)
        cleanup_cert_files(cert_path, key_path)

    def test_fingerprint_consistent(self):
        cert_path, key_path = generate_cert()
        fp1 = cert_fingerprint(cert_path)
        fp2 = cert_fingerprint(cert_path)
        assert fp1 == fp2
        cleanup_cert_files(cert_path, key_path)

    def test_different_certs_different_fingerprints(self):
        c1, k1 = generate_cert()
        c2, k2 = generate_cert()
        fp1 = cert_fingerprint(c1)
        fp2 = cert_fingerprint(c2)
        assert fp1 != fp2
        cleanup_cert_files(c1, k1)
        cleanup_cert_files(c2, k2)


class TestSSLContext:

    def test_server_ssl_context(self):
        cert_path, key_path = generate_cert()
        ctx = create_server_ssl_context(cert_path, key_path)
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2
        cleanup_cert_files(cert_path, key_path)

    def test_client_ssl_context(self):
        ctx = create_client_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2

    def test_client_ssl_context_with_fingerprint(self):
        ctx = create_client_ssl_context(expected_fingerprint="abc123")
        assert isinstance(ctx, ssl.SSLContext)


class TestCleanup:

    def test_cleanup_removes_files(self):
        cert_path, key_path = generate_cert()
        assert Path(cert_path).exists()
        cleanup_cert_files(cert_path, key_path)
        assert not Path(cert_path).exists()
        assert not Path(key_path).exists()

    def test_cleanup_nonexistent_files_no_error(self):
        cleanup_cert_files("/tmp/nonexistent_cert.pem", "/tmp/nonexistent_key.pem")
