import inspect
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import ScalarResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.db.models import Comment, Thread, User


def sql(statement):
    return str(statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    ))


class CrudTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = MagicMock(spec=AsyncSession)
        self.session.scalars.return_value = MagicMock(spec=ScalarResult)

    def tearDown(self):
        self.session.commit.assert_not_called()
        self.session.rollback.assert_not_called()
        self.session.close.assert_not_called()

    async def test_create_entities_flush_and_refresh(self):
        for function, data, model in (
            (crud.create_user, {"login": "author", "password_hash": "hash"}, User),
            (crud.create_thread, {"title": "Тред", "text": "Текст", "created_by": 1}, Thread),
            (crud.create_comment, {"thread_id": 2, "user_id": 1, "text": "Ответ"}, Comment),
        ):
            with self.subTest(model=model.__name__):
                self.session.reset_mock()
                result = await function(self.session, **data)
                self.assertIsInstance(result, model)
                for name, value in data.items():
                    self.assertEqual(getattr(result, name), value)
                self.session.add.assert_called_once_with(result)
                self.session.flush.assert_awaited_once_with()
                self.session.refresh.assert_awaited_once_with(result)

    async def test_get_queries(self):
        for function, args, kwargs, fragments in (
            (crud.get_user, (1,), {}, ("users.id = 1", "users.password_hash")),
            (crud.get_user_by_login, ("ExactLogin",), {}, ("users.login = 'ExactLogin'",)),
            (crud.get_thread, (2,), {}, ("threads.id = 2", "threads.text")),
            (crud.get_comment, (3,), {"thread_id": 2}, ("comments.id = 3", "comments.thread_id = 2")),
        ):
            with self.subTest(function=function.__name__):
                self.session.scalar.reset_mock()
                self.session.scalar.return_value = None
                self.assertIsNone(await function(self.session, *args, **kwargs))
                query = sql(self.session.scalar.call_args.args[0])
                for fragment in fragments:
                    self.assertIn(fragment, query)

    async def test_updates_only_change_allowed_fields(self):
        cases = (
            (crud.update_user_login, User(id=1, login="old", password_hash="hash", role="moderator"),
             {"login": "new"}, {"role": "moderator", "password_hash": "hash"}),
            (crud.update_user_password_hash, User(id=1, login="old", password_hash="hash", role="user"),
             {"password_hash": "new-hash"}, {"login": "old", "role": "user"}),
            (crud.update_thread, Thread(id=2, title="old", text="old", created_by=1),
             {"title": "new", "text": "new-text"}, {"created_by": 1}),
            (crud.update_comment, Comment(id=3, thread_id=2, user_id=1, text="old"),
             {"thread_id": 2, "text": "new"}, {"user_id": 1, "thread_id": 2}),
        )
        for function, instance, changes, preserved in cases:
            with self.subTest(function=function.__name__):
                self.session.reset_mock()
                self.session.scalar.return_value = instance
                result = await function(self.session, instance.id, **changes)
                self.assertIs(result, instance)
                for field, value in {**changes, **preserved}.items():
                    self.assertEqual(getattr(instance, field), value)
                self.session.flush.assert_awaited_once()

    async def test_missing_updates_and_deletes(self):
        for function, kwargs, expected in (
            (crud.update_user_login, {"login": "new"}, None),
            (crud.update_user_password_hash, {"password_hash": "hash"}, None),
            (crud.update_thread, {"title": "new", "text": "text"}, None),
            (crud.update_comment, {"thread_id": 2, "text": "text"}, None),
            (crud.delete_thread, {}, False),
            (crud.delete_comment, {"thread_id": 2}, False),
        ):
            with self.subTest(function=function.__name__):
                self.session.reset_mock()
                self.session.scalar.return_value = None
                self.assertIs(await function(self.session, 100, **kwargs), expected)
                self.session.flush.assert_not_awaited()
                self.session.delete.assert_not_awaited()

    async def test_orm_deletes(self):
        for function, instance, kwargs in (
            (crud.delete_thread, Thread(id=2), {}),
            (crud.delete_comment, Comment(id=3, thread_id=2), {"thread_id": 2}),
        ):
            with self.subTest(function=function.__name__):
                self.session.reset_mock()
                self.session.scalar.return_value = instance
                self.assertTrue(await function(self.session, instance.id, **kwargs))
                self.session.delete.assert_awaited_once_with(instance)
                self.session.flush.assert_awaited_once()

    async def test_user_delete_uses_returning_and_session_synchronization(self):
        for returned, expected in ((1, True), (None, False)):
            self.session.reset_mock()
            self.session.scalar.return_value = returned
            self.assertIs(await crud.delete_user(self.session, 1), expected)
            statement = self.session.scalar.call_args.args[0]
            query = sql(statement)
            self.assertIn("DELETE FROM users WHERE users.id = 1 RETURNING users.id", query)
            self.assertEqual(statement.get_execution_options()["synchronize_session"], "fetch")
            self.session.flush.assert_awaited_once()
            self.session.delete.assert_not_called()

    async def test_integrity_errors_are_propagated(self):
        error = IntegrityError("test", {}, Exception("constraint"))
        self.session.flush.side_effect = error
        with self.assertRaises(IntegrityError):
            await crud.create_user(self.session, login="duplicate", password_hash="hash")
        self.session.flush.side_effect = None
        self.session.scalar.side_effect = error
        with self.assertRaises(IntegrityError):
            await crud.delete_user(self.session, 1)

    async def test_pagination_queries_and_boundaries(self):
        for function, filters, table, ordering in (
            (crud.list_threads, {}, "threads", "threads.created_at DESC, threads.id DESC"),
            (crud.list_comments, {"thread_id": 7}, "comments", "comments.created_at ASC, comments.id ASC"),
        ):
            for page, size in ((1, 1), (1, 20), (2, 20), (2, 100), (100, 20)):
                with self.subTest(function=function.__name__, page=page, size=size):
                    self.session.reset_mock()
                    self.session.scalar.return_value = 23
                    self.session.scalars.return_value.all.return_value = []
                    self.assertEqual(
                        await function(self.session, page=page, page_size=size, **filters),
                        ([], 23),
                    )
                    count = sql(self.session.scalar.call_args.args[0])
                    query = sql(self.session.scalars.call_args.args[0])
                    self.assertIn(f"count(*) AS count_1 \nFROM {table}", count)
                    self.assertNotIn("LIMIT", count)
                    self.assertNotIn("OFFSET", count)
                    self.assertNotIn("ORDER BY", count)
                    self.assertIn(f"ORDER BY {ordering}", query)
                    self.assertIn(f"LIMIT {size} OFFSET {(page - 1) * size}", query)
                    if filters:
                        self.assertIn("comments.thread_id = 7", count)
                        self.assertIn("comments.thread_id = 7", query)
                    else:
                        self.assertIn("JOIN users", query)
                        self.assertNotIn("threads.text", query)
                        self.assertNotIn("password_hash", query)
                        self.assertNotIn("comments", query)

    async def test_lists_return_items_and_zero_total(self):
        for function, kwargs, item in (
            (crud.list_threads, {}, Thread(id=1)),
            (crud.list_comments, {"thread_id": 1}, Comment(id=1)),
        ):
            self.session.scalar.return_value = 1
            self.session.scalars.return_value.all.return_value = [item]
            self.assertEqual(await function(self.session, **kwargs), ([item], 1))
            self.session.scalar.return_value = 0
            self.session.scalars.return_value.all.return_value = []
            self.assertEqual(await function(self.session, **kwargs), ([], 0))

    async def test_invalid_pagination_never_queries_database(self):
        for function, kwargs in ((crud.list_threads, {}), (crud.list_comments, {"thread_id": 1})):
            for page, size in (
                (0, 20), (-1, 20), (True, 20), (1.5, 20), ("1", 20),
                (1, 0), (1, -1), (1, 101), (1, True), (1, 1.5), (1, "20"),
            ):
                with self.subTest(function=function.__name__, page=page, size=size):
                    self.session.reset_mock()
                    with self.assertRaises(ValueError):
                        await function(self.session, page=page, page_size=size, **kwargs)
                    self.session.scalar.assert_not_called()
                    self.session.scalars.assert_not_called()

    def test_interfaces_do_not_accept_role_or_update_authorship(self):
        for function in (
            crud.create_user, crud.update_user_login, crud.update_user_password_hash,
            crud.update_thread, crud.update_comment,
        ):
            params = inspect.signature(function).parameters
            self.assertNotIn("role", params)
            self.assertNotIn("created_by", params)
            if function in (crud.update_thread, crud.update_comment):
                self.assertNotIn("user_id", params)
            self.assertFalse(any(p.kind == p.VAR_KEYWORD for p in params.values()))

    def test_import_without_database_settings(self):
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith("POSTGRES_")}
        result = subprocess.run(
            [sys.executable, "-B", "-c", (
                "import sys; import app.db.crud; "
                "assert 'app.config' not in sys.modules; "
                "assert 'app.db.session' not in sys.modules"
            )],
            cwd=Path(__file__).resolve().parents[1], env=env,
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
