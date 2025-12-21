from .env import USE_HASH


def hash(s: str) -> str:
    return s


def verify(hash: str, password: str) -> bool:
    return hash == password


if USE_HASH:
    import argon2
    from argon2.exceptions import VerifyMismatchError

    hasher = argon2.PasswordHasher()

    def _hash(s: str):
        return hasher.hash(s)

    def _verify(hash: str, password: str):
        try:
            return hasher.verify(hash, password)
        except VerifyMismatchError:
            return False

    hash = _hash
    verify = _verify
