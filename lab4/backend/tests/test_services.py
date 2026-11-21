from datetime import datetime, timezone
import ast
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Comment, Thread, User
from app.schemas import (
    CommentCreate, CommentRead, CommentUpdate, ThreadCreate, ThreadRead, ThreadUpdate,
    UserCreate, UserLogin, UserLoginUpdate, UserPasswordUpdate, UserRead,
)
from app.services.auth import AuthService
from app.services.comments import CommentService
from app.services.common import transaction
from app.services.exceptions import (
    AccountHasContent, AuthenticationRequired, CommentNotFound, CsrfValidationFailed,
    InvalidCredentials, InvalidPagination, LoginAlreadyExists, PermissionDenied,
    SessionExpired, ThreadNotFound,
)
from app.services.threads import ThreadService
from app.services.users import UserService


def integrity_error(state, constraint):
    cause = Exception("Не выводить содержимое SQL")
    cause.sqlstate = state
    cause.constraint_name = constraint
    wrapped = Exception("adapter")
    wrapped.__cause__ = cause
    return IntegrityError("test", {}, wrapped)


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = MagicMock(spec=AsyncSession)
        self.client_session = {}
        self.actor = UserRead(id=1, login="author", role="user")
        self.moderator = UserRead(id=2, login="moderator", role="moderator")
        self.stranger = UserRead(id=3, login="other", role="user")
        self.stamp = datetime(2026, 11, 17, tzinfo=timezone.utc)
        self.user = User(id=1, login="author", password_hash="hash", role="user")
        self.thread = Thread(id=10, title="Тред", text="Текст", created_by=1, created_at=self.stamp, author=self.user)
        self.comment = Comment(id=20, thread_id=10, user_id=1, text="Ответ", created_at=self.stamp)

    def tearDown(self):
        self.session.begin.assert_not_called()
        self.session.close.assert_not_called()

    async def test_register_converts_and_commits(self):
        with patch("app.services.auth.hash_password", return_value="hashed") as hash_mock, \
             patch("app.db.crud.create_user", return_value=self.user) as create:
            result = await AuthService(self.session, self.client_session).register(UserCreate(login="author", password=" original "))
            self.assertIsInstance(result, UserRead)
            hash_mock.assert_awaited_once_with(" original ")
            create.assert_awaited_once_with(self.session, login="author", password_hash="hashed")
        self.session.commit.assert_awaited_once()
        self.session.rollback.assert_not_awaited()
        self.assertEqual(self.client_session, {})

    async def test_login_rotates_session_and_validates_against_database(self):
        context = {"csrf_token": "old", "user_id": 99, "role": "moderator"}
        service = AuthService(self.session, context, ttl=30)
        with patch("app.db.crud.get_user_by_login", return_value=self.user), \
             patch("app.services.auth.verify_password", return_value=True), \
             patch("app.services.auth.time.time", return_value=1000):
            result = await service.login(UserLogin(login="author", password="secret"))
        self.assertIsInstance(result, UserRead)
        self.assertEqual(context["user_id"], 1)
        self.assertEqual(context["expires_at"], 1030)
        self.assertNotIn("role", context)
        self.assertNotIn("password_hash", context)
        self.assertNotEqual(context["csrf_token"], "old")
        self.user.role = "moderator"
        with patch("app.db.crud.get_user", return_value=self.user), \
             patch("app.services.auth.time.time", return_value=1001):
            self.assertEqual((await service.current_user()).role, "moderator")
            self.assertEqual(context["expires_at"], 1030)
        self.session.commit.assert_not_called()

    async def test_bad_login_is_identical_and_preserves_session(self):
        for user in (None, self.user):
            context = {"csrf_token": "unchanged"}
            with patch("app.db.crud.get_user_by_login", return_value=user), \
                 patch("app.services.auth.verify_password", return_value=False) as verify:
                with self.assertRaises(InvalidCredentials):
                    await AuthService(self.session, context).login(UserLogin(login="author", password="secret"))
                verify.assert_awaited_once_with(user.password_hash if user else None, "secret")
            self.assertEqual(context, {"csrf_token": "unchanged"})

    async def test_anonymous_invalid_and_expired_sessions(self):
        for context, expected in (
            ({}, AuthenticationRequired),
            ({"user_id": True}, AuthenticationRequired),
            ({"user_id": 1, "issued_at": 1, "expires_at": 2}, SessionExpired),
            ({"user_id": 1, "issued_at": 101, "expires_at": 200}, AuthenticationRequired),
            ({"user_id": 1, "issued_at": "1", "expires_at": 200}, AuthenticationRequired),
        ):
            with self.subTest(context=context), patch("app.services.auth.time.time", return_value=100):
                with self.assertRaises(expected):
                    await AuthService(self.session, context).current_user()
        with patch("app.db.crud.get_user", return_value=None), patch("app.services.auth.time.time", return_value=100):
            with self.assertRaises(AuthenticationRequired):
                await AuthService(self.session, {"user_id": 1, "issued_at": 1, "expires_at": 200}).current_user()

    def test_csrf_and_logout(self):
        context = {}
        service = AuthService(self.session, context)
        token = service.csrf().csrf_token
        self.assertEqual(service.csrf().csrf_token, token)
        service.validate_csrf(token)
        for invalid in (None, "", "wrong", "не-ASCII"):
            with self.assertRaises(CsrfValidationFailed):
                service.validate_csrf(invalid)
        service.logout()
        self.assertEqual(context, {})
        with self.assertRaises(CsrfValidationFailed):
            service.validate_csrf(token)

    async def test_thread_create_uses_actor_not_request(self):
        with patch("app.db.crud.create_thread", return_value=self.thread) as create:
            result = await ThreadService(self.session).create(ThreadCreate(title="Тред", text="Текст"), self.actor)
            self.assertIsInstance(result, ThreadRead)
            create.assert_awaited_once_with(self.session, title="Тред", text="Текст", created_by=1)
        self.session.commit.assert_awaited_once()

    async def test_author_and_moderator_can_edit_and_delete(self):
        for actor in (self.actor, self.moderator):
            with patch("app.db.crud.get_thread", return_value=self.thread), \
                 patch("app.db.crud.update_thread", return_value=self.thread), \
                 patch("app.db.crud.delete_thread", return_value=True), \
                 patch("app.db.crud.get_comment", return_value=self.comment), \
                 patch("app.db.crud.update_comment", return_value=self.comment), \
                 patch("app.db.crud.delete_comment", return_value=True):
                await ThreadService(self.session).update(10, ThreadUpdate(title="Тред", text="Текст"), actor)
                await ThreadService(self.session).delete(10, actor)
                await CommentService(self.session).update(10, 20, CommentUpdate(text="Ответ"), actor)
                await CommentService(self.session).delete(10, 20, actor)
        self.assertEqual(self.session.commit.await_count, 8)

    async def test_stranger_is_rejected_before_update(self):
        with patch("app.db.crud.get_thread", return_value=self.thread), \
             patch("app.db.crud.get_comment", return_value=self.comment), \
             patch("app.db.crud.update_thread") as update_thread, \
             patch("app.db.crud.delete_thread") as delete_thread, \
             patch("app.db.crud.update_comment") as update_comment, \
             patch("app.db.crud.delete_comment") as delete_comment:
            for action in (
                lambda: ThreadService(self.session).update(10, ThreadUpdate(title="x", text="x"), self.stranger),
                lambda: ThreadService(self.session).delete(10, self.stranger),
                lambda: CommentService(self.session).update(10, 20, CommentUpdate(text="x"), self.stranger),
                lambda: CommentService(self.session).delete(10, 20, self.stranger),
            ):
                with self.assertRaises(PermissionDenied):
                    await action()
            for mock in (update_thread, delete_thread, update_comment, delete_comment):
                mock.assert_not_awaited()
        self.session.commit.assert_not_called()
        self.assertEqual(self.session.rollback.await_count, 4)

    async def test_comment_parent_scope_and_empty_page(self):
        service = CommentService(self.session)
        with patch("app.db.crud.get_thread", return_value=None):
            with self.assertRaises(ThreadNotFound):
                await service.list(999)
        with patch("app.db.crud.get_thread", return_value=self.thread), \
             patch("app.db.crud.list_comments", return_value=([], 0)):
            result = await service.list(10)
            self.assertEqual(result.items, [])
            self.assertEqual(result.total_pages, 0)
        with patch("app.db.crud.get_thread", return_value=self.thread), \
             patch("app.db.crud.get_comment", return_value=None) as get:
            with self.assertRaises(CommentNotFound):
                await service.get(10, 99)
            get.assert_awaited_once_with(self.session, 99, thread_id=10)

    async def test_comment_create_and_read_convert_dtos(self):
        service = CommentService(self.session)
        with patch("app.db.crud.get_thread", return_value=self.thread), \
             patch("app.db.crud.create_comment", return_value=self.comment) as create, \
             patch("app.db.crud.get_comment", return_value=self.comment):
            result = await service.create(10, CommentCreate(text="Ответ"), self.actor)
            self.assertIsInstance(result, CommentRead)
            create.assert_awaited_once_with(self.session, thread_id=10, user_id=1, text="Ответ")
            self.assertIsInstance(await service.get(10, 20), CommentRead)

    async def test_list_converts_summary_and_pagination_errors(self):
        with patch("app.db.crud.list_threads", return_value=([self.thread], 21)) as listed:
            result = await ThreadService(self.session).list(page=2)
            self.assertEqual(result.total_pages, 2)
            self.assertNotIn("text", result.items[0].model_dump())
            self.assertNotIn("password", result.model_dump_json())
            listed.assert_awaited_once_with(self.session, page=2, page_size=20)
        for page, size in ((0, 20), (True, 20), (1, 101), (1, 1.5)):
            with self.assertRaises(InvalidPagination):
                await ThreadService(self.session).list(page=page, page_size=size)
        self.session.commit.assert_not_called()

    async def test_concurrent_disappearance(self):
        with patch("app.db.crud.get_thread", return_value=self.thread), \
             patch("app.db.crud.update_thread", return_value=None), \
             patch("app.db.crud.delete_thread", return_value=False):
            with self.assertRaises(ThreadNotFound):
                await ThreadService(self.session).update(10, ThreadUpdate(title="x", text="x"), self.actor)
            with self.assertRaises(ThreadNotFound):
                await ThreadService(self.session).delete(10, self.actor)
        self.session.commit.assert_not_called()

    async def test_commit_and_conversion_errors_rollback(self):
        with patch("app.db.crud.create_thread", return_value=self.thread):
            self.session.commit.side_effect = RuntimeError("commit failed")
            with self.assertRaises(RuntimeError):
                await ThreadService(self.session).create(ThreadCreate(title="x", text="x"), self.actor)
        self.session.rollback.assert_awaited_once()
        self.session.reset_mock()
        self.session.commit.side_effect = None
        with patch("app.db.crud.create_thread", return_value=Thread(id=1)):
            with self.assertRaises(ValidationError):
                await ThreadService(self.session).create(ThreadCreate(title="x", text="x"), self.actor)
        self.session.commit.assert_not_awaited()
        self.session.rollback.assert_awaited_once()

    async def test_known_and_unknown_constraints(self):
        for state, name, expected in (
            ("23505", "ix_users_login", LoginAlreadyExists),
            ("23505", "unknown", IntegrityError),
            ("23503", "ix_users_login", IntegrityError),
        ):
            self.session.reset_mock()
            self.session.commit.side_effect = integrity_error(state, name)
            with self.assertRaises(expected):
                async with transaction(self.session, conflicts={("23505", "ix_users_login"): LoginAlreadyExists}):
                    pass
            self.session.rollback.assert_awaited_once()

    async def test_profile_and_password(self):
        service = UserService(self.session, self.client_session)
        with patch("app.db.crud.update_user_login", return_value=self.user) as update:
            self.assertIsInstance(await service.update_login(UserLoginUpdate(login="author"), self.actor), UserRead)
            update.assert_awaited_once_with(self.session, 1, login="author")
        with patch("app.db.crud.get_user", return_value=self.user), \
             patch("app.services.users.verify_password", return_value=False), \
             patch("app.db.crud.update_user_password_hash") as update:
            with self.assertRaises(InvalidCredentials):
                await service.update_password(UserPasswordUpdate(current_password="bad", new_password="new"), self.actor)
            update.assert_not_called()
        with patch("app.db.crud.get_user", return_value=self.user), \
             patch("app.services.users.verify_password", return_value=True), \
             patch("app.services.users.hash_password", return_value="new-hash"), \
             patch("app.db.crud.update_user_password_hash", return_value=self.user) as update:
            await service.update_password(UserPasswordUpdate(current_password="old", new_password="new"), self.actor)
            update.assert_awaited_once_with(self.session, 1, password_hash="new-hash")

    def test_services_do_not_depend_on_http(self):
        for path in (Path(__file__).parents[1] / "app" / "services").glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith(("fastapi", "starlette", "app.api")))
                elif isinstance(node, ast.Import):
                    self.assertFalse(any(item.name.startswith(("fastapi", "starlette", "app.api")) for item in node.names))

    async def test_delete_account_clears_session_only_after_commit(self):
        self.client_session.update(user_id=1)
        service = UserService(self.session, self.client_session)
        with patch("app.db.crud.delete_user", side_effect=integrity_error("23503", "threads_created_by_fkey")):
            with self.assertRaises(AccountHasContent):
                await service.delete(self.actor)
        self.assertEqual(self.client_session, {"user_id": 1})
        with patch("app.db.crud.delete_user", return_value=True):
            await service.delete(self.actor)
        self.assertEqual(self.client_session, {})


if __name__ == "__main__":
    unittest.main()
