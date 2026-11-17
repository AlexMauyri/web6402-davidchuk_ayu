"""Только отдельная тестовая PostgreSQL: TEST_DATABASE_URL=postgresql+asyncpg://... .

Каждый тест создаёт временную схему в транзакции, которая полностью откатывается.
Настройки приложения и его .env не используются.
"""

from datetime import datetime, timezone
import os
import unittest
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db import crud
from app.db.base import Base
from app.schemas import ThreadListItem


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "Не задан DSN отдельной тестовой PostgreSQL")
class CrudIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        self.addAsyncCleanup(self.engine.dispose)
        self.connection = await self.engine.connect()
        self.addAsyncCleanup(self.connection.close)
        self.transaction = await self.connection.begin()
        self.addAsyncCleanup(self.transaction.rollback)
        schema = f"crud_test_{uuid4().hex}"
        await self.connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await self.connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        await self.connection.run_sync(Base.metadata.create_all)
        self.session = AsyncSession(
            bind=self.connection, expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        self.addAsyncCleanup(self.session.close)

    async def create_fixture(self):
        user = await crud.create_user(self.session, login="author", password_hash="hash")
        thread = await crud.create_thread(
            self.session, title="Тред", text="Текст", created_by=user.id,
        )
        comment = await crud.create_comment(
            self.session, thread_id=thread.id, user_id=user.id, text="Ответ",
        )
        return user, thread, comment

    async def test_full_crud_and_cascade(self):
        user, thread, comment = await self.create_fixture()
        user_id, thread_id, comment_id = user.id, thread.id, comment.id
        self.assertEqual(user.role, "user")
        self.assertIsNotNone(thread.created_at.utcoffset())
        self.assertIsNotNone(comment.created_at.utcoffset())
        self.assertEqual((await crud.get_user_by_login(self.session, "author")).id, user_id)
        await crud.update_user_login(self.session, user_id, login="new")
        await crud.update_user_password_hash(self.session, user_id, password_hash="new-hash")
        await crud.update_thread(self.session, thread_id, title="Новое", text="Новый текст")
        await crud.update_comment(self.session, comment_id, thread_id=thread_id, text="Изменён")
        self.assertEqual((await crud.get_user(self.session, user_id)).password_hash, "new-hash")
        self.assertEqual((await crud.get_thread(self.session, thread_id)).title, "Новое")
        self.assertEqual((await crud.get_comment(self.session, comment_id, thread_id=thread_id)).text, "Изменён")
        self.assertTrue(await crud.delete_comment(self.session, comment_id, thread_id=thread_id))
        self.assertFalse(await crud.delete_comment(self.session, comment_id, thread_id=thread_id))
        await crud.create_comment(self.session, thread_id=thread_id, user_id=user_id, text="Каскад")
        self.assertTrue(await crud.delete_thread(self.session, thread_id))
        self.assertEqual(await crud.list_comments(self.session, thread_id=thread_id), ([], 0))
        self.assertTrue(await crud.delete_user(self.session, user_id))
        self.assertFalse(await crud.delete_user(self.session, user_id))

    async def test_pagination_and_scoped_comments(self):
        user, thread, _ = await self.create_fixture()
        other = await crud.create_thread(self.session, title="Другой", text="Текст", created_by=user.id)
        ids = []
        stamp = datetime(2026, 11, 17, tzinfo=timezone.utc)
        for i in range(4):
            comment = await crud.create_comment(
                self.session, thread_id=other.id, user_id=user.id, text=str(i),
            )
            comment.created_at = stamp
            ids.append(comment.id)
        thread.created_at = other.created_at = stamp
        await self.session.flush()
        first, total = await crud.list_threads(self.session, page_size=1)
        second, _ = await crud.list_threads(self.session, page=2, page_size=1)
        self.assertEqual(total, 2)
        self.assertEqual([first[0].id, second[0].id], [other.id, thread.id])
        first, total = await crud.list_comments(self.session, thread_id=other.id, page_size=2)
        second, _ = await crud.list_comments(self.session, thread_id=other.id, page=2, page_size=2)
        self.assertEqual(total, 4)
        self.assertEqual([c.id for c in first + second], ids)
        self.assertEqual(await crud.list_comments(self.session, thread_id=other.id, page=3, page_size=2), ([], 4))
        self.assertIsNone(await crud.get_comment(self.session, ids[0], thread_id=thread.id))
        self.assertIsNone(await crud.update_comment(self.session, ids[0], thread_id=thread.id, text="Нет"))
        self.assertFalse(await crud.delete_comment(self.session, ids[0], thread_id=thread.id))

    async def test_summary_loading_and_full_reload(self):
        user, thread, _ = await self.create_fixture()
        user_id, thread_id = user.id, thread.id
        await self.session.commit()
        self.session.expunge_all()
        items, _ = await crud.list_threads(self.session)
        item = items[0]
        self.assertIn("text", inspect(item).unloaded)
        self.assertIn("password_hash", inspect(item.author).unloaded)
        with self.assertRaises(InvalidRequestError):
            _ = item.text
        full = await crud.get_thread(self.session, thread_id)
        self.assertIs(full, item)
        self.assertEqual(full.text, "Текст")
        full_user = await crud.get_user(self.session, user_id)
        self.assertEqual(full_user.password_hash, "hash")
        await self.session.close()
        self.assertEqual(ThreadListItem.model_validate(item).author.login, "author")

    async def test_constraints_and_external_transaction_control(self):
        user, thread, _ = await self.create_fixture()
        user_id, thread_id = user.id, thread.id
        await self.session.commit()
        with self.assertRaises(IntegrityError):
            await crud.create_user(self.session, login="author", password_hash="duplicate")
        await self.session.rollback()
        self.assertIsNotNone(await crud.get_user(self.session, user_id))
        with self.assertRaises(IntegrityError):
            await crud.delete_user(self.session, user_id)
        await self.session.rollback()
        with self.assertRaises(IntegrityError):
            await crud.create_comment(self.session, thread_id=thread_id + 1000, user_id=user_id, text="Нет FK")
        await self.session.rollback()
        await crud.update_thread(self.session, thread_id, title="Откат", text="Изменён")
        await self.session.rollback()
        self.assertEqual((await crud.get_thread(self.session, thread_id)).title, "Тред")
        await crud.update_thread(self.session, thread_id, title="Сохранён", text="Текст")
        await self.session.commit()
        async with AsyncSession(bind=self.connection, join_transaction_mode="create_savepoint") as observer:
            self.assertEqual((await crud.get_thread(observer, thread_id)).title, "Сохранён")


if __name__ == "__main__":
    unittest.main()
