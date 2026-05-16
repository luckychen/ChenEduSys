"""Unit tests for hub server auth (password hashing, JWT)."""

from __future__ import annotations

from hub_server.auth import (
    create_token,
    decode_token,
    hash_password,
    new_id,
    verify_password,
)


class TestPasswordHashing:

    def test_hash_and_verify_match(self):
        pw_hash = hash_password("secret123")
        assert verify_password("secret123", pw_hash)

    def test_wrong_password_fails(self):
        pw_hash = hash_password("secret123")
        assert not verify_password("wrong", pw_hash)

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2  # argon2 uses random salt


class TestJWT:

    def test_create_and_decode_token(self):
        token = create_token("user1", "alice", "teacher")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user1"
        assert payload["username"] == "alice"
        assert payload["role"] == "teacher"

    def test_expired_token_returns_none(self):
        import hub_server.auth as mod
        old = mod._jwt_expiry_seconds
        mod._jwt_expiry_seconds = -1  # already expired
        token = create_token("user1", "alice", "student")
        mod._jwt_expiry_seconds = old
        assert decode_token(token) is None

    def test_tampered_token_returns_none(self):
        token = create_token("user1", "alice", "student")
        tampered = token[:-5] + "XXXXX"
        assert decode_token(tampered) is None

    def test_invalid_token_returns_none(self):
        assert decode_token("not-a-token") is None

    def test_new_id_length(self):
        assert len(new_id()) == 12

    def test_new_id_unique(self):
        ids = {new_id() for _ in range(100)}
        assert len(ids) == 100
