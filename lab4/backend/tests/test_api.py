import ast
import base64
import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

# Тесты не читают личный .env.local и не подключаются к БД.
_ENV = {
    "POSTGRES_HOST": "localhost", "POSTGRES_PORT": "5433",
    "POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test", "POSTGRES_DB": "test",
    "SESSION_SECRET_KEY": "test-only-signing-key-not-for-production-123456",
}
with patch.dict(os.environ, _ENV), patch(
    "pydantic_settings.sources.providers.dotenv.DotEnvSettingsSource._read_env_files",
    return_value={},
):
    from app.config import Settings
    from app.main import create_app

from app.api.dependencies import get_current_user, get_thread_service
from app.db.models import User
from app.db.session import get_session
from app.schemas import Page, ThreadListItem, UserRead
from app.services.exceptions import (
    AccountHasContent, InvalidCredentials, PermissionDenied, ThreadNotFound,
)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.config = Settings(_env_file=None, **_ENV)
        self.app = create_app(self.config)
        self.db = MagicMock(spec=AsyncSession)
        async def session():
            yield self.db
        self.app.dependency_overrides[get_session] = session
        self.client = TestClient(self.app, base_url="https://testserver", raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.user = User(id=1, login="author", password_hash="hash", role="user")
        self.actor = UserRead(id=1, login="author", role="user")

    def csrf(self):
        response = self.client.get("/api/auth/csrf")
        self.assertEqual(response.status_code, 200)
        return {"X-CSRF-Token": response.json()["csrf_token"]}

    def test_cookie_flow_login_rotation_and_logout(self):
        headers = self.csrf()
        self.assertEqual(self.client.get("/api/users/me").status_code, 401)
        cookie = self.client.cookies.get("forum_session")
        payload = json.loads(base64.b64decode(cookie.split(".")[0]))
        self.assertEqual(set(payload), {"csrf_token"})
        with patch("app.db.crud.get_user_by_login", return_value=self.user), \
             patch("app.services.auth.verify_password", return_value=True), \
             patch("app.db.crud.get_user", return_value=self.user):
            response = self.client.post("/api/auth/login", json={"login": "author", "password": "secret"}, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"id": 1, "login": "author", "role": "user"})
            self.assertNotIn("access_token", response.json())
            self.assertEqual(self.client.get("/api/users/me").status_code, 200)
            self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 403)
            headers = self.csrf()
            self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 204)
            self.assertIsNone(self.client.cookies.get("forum_session"))
            self.assertEqual(self.client.get("/api/users/me").status_code, 401)

    def test_cookie_flags_and_tampered_cookie(self):
        response = self.client.get("/api/auth/csrf")
        cookie = response.headers["set-cookie"].lower()
        for expected in ("httponly", "secure", "samesite=lax", "path=/api", "max-age=1800"):
            self.assertIn(expected, cookie)
        headers = self.csrf()
        self.client.cookies.clear()
        self.client.cookies.set("forum_session", "tampered.invalid.cookie", path="/api")
        self.assertEqual(self.client.get("/api/users/me").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 403)

    def test_absolute_session_expiry(self):
        headers = self.csrf()
        with patch("app.db.crud.get_user_by_login", return_value=self.user), \
             patch("app.services.auth.verify_password", return_value=True):
            response = self.client.post("/api/auth/login", json={"login": "author", "password": "secret"}, headers=headers)
        self.assertEqual(response.status_code, 200)
        import time
        future = int(time.time()) + self.config.session_ttl + 1
        # Подпись middleware остаётся свежей; проверяется абсолютное время сервиса.
        with patch("app.services.auth.time", **{"time.return_value": future}):
            response = self.client.get("/api/users/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "session_expired")

    def test_csrf_required_for_register_login_logout(self):
        for path in ("register", "login", "logout"):
            with self.subTest(path=path):
                response = self.client.post(f"/api/auth/{path}", json={"login": "a", "password": "b"})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["error"]["code"], "csrf_validation_failed")

    def test_register_and_login_errors(self):
        headers = self.csrf()
        with patch("app.services.auth.hash_password", return_value="hashed"), \
             patch("app.db.crud.create_user", return_value=self.user):
            response = self.client.post("/api/auth/register", json={"login": "author", "password": "secret"}, headers=headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["role"], "user")
        self.db.commit.assert_awaited_once()
        with patch("app.db.crud.get_user_by_login", return_value=None), \
             patch("app.services.auth.verify_password", return_value=False):
            response = self.client.post("/api/auth/login", json={"login": "author", "password": "secret"}, headers=headers)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("www-authenticate", response.headers)
        self.assertEqual(response.json()["error"]["code"], "invalid_credentials")

    def test_forwarding_pagination_and_dtos(self):
        service = MagicMock()
        service.list = AsyncMock(return_value=Page[ThreadListItem](items=[], total=0, page=2, page_size=5))
        self.app.dependency_overrides[get_thread_service] = lambda: service
        response = self.client.get("/api/threads?page=2&page_size=5")
        self.assertEqual(response.status_code, 200)
        service.list.assert_awaited_once_with(page=2, page_size=5)
        self.assertEqual(response.json()["total_pages"], 0)
        self.app.dependency_overrides[get_current_user] = lambda: self.actor
        service.delete = AsyncMock(return_value=None)
        response = self.client.delete("/api/threads/10", headers=self.csrf())
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        service.delete.assert_awaited_once_with(10, self.actor)

    def test_central_exception_mapping(self):
        service = MagicMock()
        self.app.dependency_overrides[get_thread_service] = lambda: service
        for error, status in (
            (InvalidCredentials(), 401), (PermissionDenied(), 403),
            (ThreadNotFound(), 404), (AccountHasContent(), 409),
        ):
            with self.subTest(error=type(error).__name__):
                service.get = AsyncMock(side_effect=error)
                response = self.client.get("/api/threads/1")
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json(), {"error": {"code": error.code, "message": error.message}})
        service.get = AsyncMock(side_effect=RuntimeError("SECRET SQL PARAMETERS"))
        response = self.client.get("/api/threads/1")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("SECRET", response.text)

    def test_validation_does_not_echo_password(self):
        headers = self.csrf()
        response = self.client.post("/api/auth/register", json={"login": "a", "password": {"value": "SECRET"}}, headers=headers)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("SECRET", response.text)
        self.assertNotIn('"input"', response.text)
        response = self.client.get("/api/threads?page=0&page_size=101")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/api/threads/0").status_code, 422)

    def test_openapi_health_and_routes(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/docs").status_code, 200)
        paths = self.client.get("/openapi.json").json()["paths"]
        expected = {
            "/api/auth/csrf": {"get"}, "/api/auth/register": {"post"},
            "/api/auth/login": {"post"}, "/api/auth/logout": {"post"},
            "/api/users/me": {"get", "delete"},
            "/api/users/me/login": {"put"}, "/api/users/me/password": {"put"},
            "/api/threads": {"get", "post"}, "/api/threads/{thread_id}": {"get", "put", "delete"},
            "/api/threads/{thread_id}/comments": {"get", "post"},
            "/api/threads/{thread_id}/comments/{comment_id}": {"get", "put", "delete"},
        }
        for path, methods in expected.items():
            self.assertEqual(set(paths[path]), methods)

    def test_api_contains_only_forwarding(self):
        for name in ("auth", "users", "threads", "comments"):
            tree = ast.parse((Path(__file__).parents[1] / "app" / "api" / f"{name}.py").read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertEqual(len(node.body), 1)
                    self.assertIsInstance(node.body[0], ast.Return)

    def test_secret_is_required_only_for_api(self):
        config = Settings(_env_file=None, **{key: value for key, value in _ENV.items() if key != "SESSION_SECRET_KEY"}, SESSION_SECRET_KEY="short")
        with self.assertRaises(ValueError):
            create_app(config)


if __name__ == "__main__":
    unittest.main()
