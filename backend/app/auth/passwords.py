"""Password hashing (argon2id) and strength rules."""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import get_settings

_hasher = PasswordHasher()
# Checked against when the email doesn't exist, so a login takes as long either way.
_DUMMY_HASH = _hasher.hash("bookmind-dummy-password-for-timing")

_COMMON = {
    "password", "password1", "password123", "123456789", "1234567890", "12345678", "qwertyuiop", "qwerty123",
    "iloveyou", "letmein123", "welcome123", "admin12345", "abc1234567", "passw0rd!", "1q2w3e4r5t", "football1",
    "baseball1", "sunshine1", "princess1", "trustno1", "bookmind123", "changeme123",
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_problem(password: str, email: str = "") -> str | None:
    """Why a password is too weak, in words for the user; None if it's fine."""
    n = get_settings().password_min_length
    if len(password) < n:
        return f"Use at least {n} characters."
    if len(password) > 256:
        return "Use at most 256 characters."
    if len(set(password)) < 4:
        return "Use a mix of different characters."
    lowered = password.lower()
    if lowered in _COMMON or lowered.rstrip("!.") in _COMMON:
        return "That password is too common. Pick something less guessable."
    local = email.split("@", 1)[0].lower()
    if len(local) >= 4 and local in lowered:
        return "Don't use your email address in your password."
    return None
