from app.core.security import get_password_hash, verify_password


def test_password_hash_and_verify_roundtrip() -> None:
    raw_password = "strong-password-123"
    hashed = get_password_hash(raw_password)

    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("wrong-password", hashed) is False
