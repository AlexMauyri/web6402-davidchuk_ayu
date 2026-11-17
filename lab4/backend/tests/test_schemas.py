import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from pydantic import TypeAdapter, ValidationError

from app.db.models import Comment, Thread, User
from app.schemas import (
    CommentCreate,
    CommentRead,
    ThreadCreate,
    ThreadListItem,
    ThreadRead,
    UserCreate,
    UserRead,
    UserSummary,
)


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.created_at = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
        self.user = User(id=1, login="author", password_hash="private-hash", role="user")
        self.thread = Thread(
            id=2,
            title="Заголовок",
            text="Текст треда",
            created_by=1,
            created_at=self.created_at,
            author=self.user,
        )
        self.comment = Comment(
            id=3,
            thread_id=2,
            user_id=1,
            text="Комментарий",
            created_at=self.created_at,
        )
        self.requests = (
            (UserCreate, {"login": "author", "password": " password "}),
            (ThreadCreate, {"title": "Заголовок", "text": "Текст"}),
            (CommentCreate, {"text": "Комментарий"}),
        )
        self.responses = (
            (UserRead, self.user, {"id", "login", "role"}),
            (UserSummary, self.user, {"id", "login"}),
            (ThreadRead, self.thread, {"id", "title", "text", "created_by", "created_at"}),
            (CommentRead, self.comment, {"id", "thread_id", "user_id", "text", "created_at"}),
            (ThreadListItem, self.thread, {"id", "title", "author", "created_at"}),
        )

    def test_valid_requests(self):
        for schema, data in self.requests:
            with self.subTest(schema=schema.__name__):
                dto = schema.model_validate(data)
                self.assertEqual(set(schema.model_fields), set(data))

    def test_request_fields_are_required_and_nonempty(self):
        for schema, data in self.requests:
            for field in data:
                with self.subTest(schema=schema.__name__, field=field):
                    missing = {key: value for key, value in data.items() if key != field}
                    with self.assertRaises(ValidationError):
                        schema.model_validate(missing)
                    with self.assertRaises(ValidationError):
                        schema.model_validate({**data, field: ""})

    def test_server_fields_and_unknown_fields_are_forbidden(self):
        for schema, data in self.requests:
            for field in (
                "id", "role", "password_hash", "created_at", "created_by",
                "user_id", "thread_id", "unexpected",
            ):
                with self.subTest(schema=schema.__name__, field=field):
                    with self.assertRaises(ValidationError):
                        schema.model_validate({**data, field: "untrusted"})

    def test_password_is_preserved_and_masked(self):
        password = " secret password "
        dto = UserCreate(login="author", password=password)
        self.assertEqual(dto.password.get_secret_value(), password)
        self.assertNotIn(password, repr(dto))
        self.assertNotIn(password, dto.model_dump_json())

    def test_responses_from_orm_have_exact_fields(self):
        for schema, source, fields in self.responses:
            with self.subTest(schema=schema.__name__):
                dto = schema.model_validate(source)
                self.assertEqual(set(schema.model_fields), fields)
                self.assertEqual(set(dto.model_dump()), fields)
                self.assertEqual(set(json.loads(dto.model_dump_json())), fields)

    def test_responses_never_expose_passwords(self):
        for schema, source, _ in self.responses:
            with self.subTest(schema=schema.__name__):
                dto = schema.model_validate(source)
                for content in (
                    json.dumps(dto.model_dump(mode="json")),
                    dto.model_dump_json(),
                    json.dumps(schema.model_json_schema()),
                ):
                    self.assertNotIn("password", content)
                    self.assertNotIn("private-hash", content)

    def test_roles(self):
        for role in ("user", "moderator"):
            self.assertEqual(UserRead(id=1, login="author", role=role).role, role)
        with self.assertRaises(ValidationError):
            UserRead(id=1, login="author", role="admin")

    def test_dates_require_timezone(self):
        for schema, source, _ in self.responses:
            if "created_at" not in schema.model_fields:
                continue
            with self.subTest(schema=schema.__name__):
                dto = schema.model_validate(source)
                self.assertEqual(dto.created_at, self.created_at)
                encoded = json.loads(dto.model_dump_json())["created_at"]
                self.assertIsNotNone(datetime.fromisoformat(encoded).utcoffset())
                with self.assertRaises(ValidationError):
                    schema.model_validate({
                        **dto.model_dump(),
                        "created_at": self.created_at.replace(tzinfo=None),
                    })

    def test_thread_list_contains_only_summary_data(self):
        adapter = TypeAdapter(list[ThreadListItem])
        items = adapter.validate_python([self.thread])
        payload = json.loads(adapter.dump_json(items))
        self.assertEqual(payload, [{
            "id": 2,
            "title": "Заголовок",
            "author": {"id": 1, "login": "author"},
            "created_at": "2026-11-17T12:00:00Z",
        }])

    def test_responses_do_not_access_unlisted_relations(self):
        class Source(SimpleNamespace):
            @property
            def author(self):
                raise AssertionError("Неожиданное чтение связи author")

            @property
            def comments(self):
                raise AssertionError("Неожиданное чтение связи comments")

            @property
            def threads(self):
                raise AssertionError("Неожиданное чтение связи threads")

        for schema, source, _ in self.responses:
            if schema is ThreadListItem:
                continue
            data = {
                field: getattr(source, field)
                for field in schema.model_fields
            }
            schema.model_validate(Source(**data))
        ThreadListItem.model_validate(SimpleNamespace(
            id=2,
            title="Заголовок",
            author=Source(id=1, login="author"),
            created_at=self.created_at,
        ))

    def test_schemas_import_without_database_settings(self):
        env = {
            key: value for key, value in os.environ.items()
            if not key.upper().startswith("POSTGRES_")
        }
        result = subprocess.run(
            [sys.executable, "-B", "-c", (
                "import sys; import app.schemas; "
                "assert 'app.config' not in sys.modules; "
                "assert 'app.db.session' not in sys.modules"
            )],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
