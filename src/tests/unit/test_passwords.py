import pytest
from src.utils.passwords import PasswordManager

pm = PasswordManager()


class TestHashAndVerify:
    def test_hash_returns_string(self):
        h = PasswordManager.hash_password("Secret@1")
        assert isinstance(h, str)
        assert h != "Secret@1"

    def test_verify_correct_password(self):
        h = PasswordManager.hash_password("Secret@1")
        assert PasswordManager.verify_password("Secret@1", h) is True

    def test_verify_wrong_password(self):
        h = PasswordManager.hash_password("Secret@1")
        assert PasswordManager.verify_password("WrongPass@1", h) is False

    def test_each_hash_is_unique(self):
        h1 = PasswordManager.hash_password("Secret@1")
        h2 = PasswordManager.hash_password("Secret@1")
        assert h1 != h2  # bcrypt salts differ


class TestPasswordStrength:
    def test_strong_password_passes(self):
        ok, msg = pm.is_strong_password("Valid@123")
        assert ok is True
        assert "strong" in msg.lower()

    def test_too_short_fails(self):
        ok, msg = pm.is_strong_password("V@1")
        assert ok is False
        assert "8 characters" in msg

    def test_no_digit_fails(self):
        ok, msg = pm.is_strong_password("NoDigit@abc")
        assert ok is False
        assert "digit" in msg

    def test_no_letter_fails(self):
        ok, msg = pm.is_strong_password("123456@789")
        assert ok is False
        assert "letter" in msg

    def test_no_special_char_fails(self):
        ok, msg = pm.is_strong_password("NoSpecial1a")
        assert ok is False
        assert "special" in msg

    def test_exactly_8_chars_with_requirements_passes(self):
        ok, _ = pm.is_strong_password("Ab1@cdef")
        assert ok is True
