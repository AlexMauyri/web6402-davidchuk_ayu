import unittest
from unittest.mock import AsyncMock, patch

from app.services.security import hash_password, new_csrf_token, verify_password


class SecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_argon2_preserves_password(self):
        password = " password with spaces "
        hashed = await hash_password(password)
        self.assertTrue(hashed.startswith("$argon2id$"))
        self.assertNotIn(password, hashed)
        self.assertTrue(await verify_password(hashed, password))
        self.assertFalse(await verify_password(hashed, password.strip()))
        self.assertFalse(await verify_password(None, "forum-dummy-password"))
        self.assertFalse(await verify_password("invalid-hash", password))

    async def test_hashing_is_offloaded(self):
        with patch("app.services.security.asyncio.to_thread", new_callable=AsyncMock) as work:
            work.return_value = "hash"
            self.assertEqual(await hash_password("secret"), "hash")
            work.assert_awaited_once()

    def test_csrf_tokens_are_random(self):
        first, second = new_csrf_token(), new_csrf_token()
        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 32)


if __name__ == "__main__":
    unittest.main()
