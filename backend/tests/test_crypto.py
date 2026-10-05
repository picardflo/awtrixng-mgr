from app.core.crypto import decrypt, encrypt, preview


def test_roundtrip():
    assert decrypt(encrypt("s3cr3t-token")) == "s3cr3t-token"


def test_ciphertext_does_not_contain_plaintext():
    assert "s3cr3t" not in encrypt("s3cr3t-token")


def test_encryption_is_not_deterministic():
    """Fernet includes an IV: two ciphertexts of the same secret differ."""
    assert encrypt("same") != encrypt("same")


def test_preview_never_leaks_the_start():
    masked = preview("abcdefgh1234")
    assert masked == "••••1234"
    assert "abcd" not in masked


def test_preview_of_short_secret_shows_nothing():
    assert preview("abc") == "••••"


def test_key_file_is_owner_only():
    import os

    from app.core.config import get_settings

    encrypt("touch")  # force key generation
    path = get_settings().secret_key_file
    if path.exists():
        assert oct(os.stat(path).st_mode)[-3:] == "600"
