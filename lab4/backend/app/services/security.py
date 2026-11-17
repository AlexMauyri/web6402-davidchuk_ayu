import asyncio
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
_dummy_hash = (
    "$argon2id$v=19$m=65536,t=3,p=4$MUxSiyUXeQZD9oJVzVpKkg$"
    "zxcJspJQkCZIYZrQOjWjO43QOfabzHOvhtgtlWx1teQ"
)


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        valid = await asyncio.to_thread(_hasher.verify, password_hash or _dummy_hash, password)
    except (VerificationError, InvalidHashError):
        return False
    return valid and password_hash is not None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
