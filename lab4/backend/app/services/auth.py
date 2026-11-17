from collections.abc import MutableMapping
import secrets
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.db.sqlstate import UNIQUE_VIOLATION
from app.schemas import CsrfRead, UserCreate, UserLogin, UserRead
from app.services.common import transaction
from app.services.exceptions import (
    AuthenticationRequired, CsrfValidationFailed, InvalidCredentials,
    LoginAlreadyExists, SessionExpired,
)
from app.services.security import hash_password, new_csrf_token, verify_password


class AuthService:
    def __init__(
        self, session: AsyncSession, client_session: MutableMapping[str, Any],
        *, ttl: int = 1800,
    ):
        self.session = session
        self.client_session = client_session
        self.ttl = ttl

    def csrf(self) -> CsrfRead:
        token = self.client_session.get("csrf_token")
        if not isinstance(token, str) or not token:
            token = new_csrf_token()
            self.client_session["csrf_token"] = token
        return CsrfRead(csrf_token=token)

    def validate_csrf(self, token: str | None) -> None:
        expected = self.client_session.get("csrf_token")
        if not isinstance(expected, str) or not expected or not isinstance(token, str):
            raise CsrfValidationFailed()
        if not secrets.compare_digest(expected.encode(), token.encode()):
            raise CsrfValidationFailed()

    async def register(self, data: UserCreate) -> UserRead:
        async with transaction(
            self.session, conflicts={(UNIQUE_VIOLATION, "ix_users_login"): LoginAlreadyExists},
        ):
            password_hash = await hash_password(data.password.get_secret_value())
            user = await crud.create_user(self.session, login=data.login, password_hash=password_hash)
            result = UserRead.model_validate(user)
        return result

    async def login(self, data: UserLogin) -> UserRead:
        user = await crud.get_user_by_login(self.session, data.login)
        valid = await verify_password(
            user.password_hash if user is not None else None,
            data.password.get_secret_value(),
        )
        if not valid or user is None:
            raise InvalidCredentials()
        result = UserRead.model_validate(user)
        now = int(time.time())
        self.client_session.clear()
        self.client_session.update(
            user_id=user.id, issued_at=now, expires_at=now + self.ttl,
            csrf_token=new_csrf_token(),
        )
        return result

    async def current_user(self) -> UserRead:
        user_id = self.client_session.get("user_id")
        issued_at = self.client_session.get("issued_at")
        expires_at = self.client_session.get("expires_at")
        if type(user_id) is not int or user_id < 1:
            raise AuthenticationRequired()
        if type(issued_at) is not int or type(expires_at) is not int:
            raise AuthenticationRequired()
        now = int(time.time())
        if issued_at > now or expires_at <= issued_at:
            raise AuthenticationRequired()
        if expires_at <= now:
            raise SessionExpired()
        user = await crud.get_user(self.session, user_id)
        if user is None:
            raise AuthenticationRequired()
        return UserRead.model_validate(user)

    def logout(self) -> None:
        self.client_session.clear()
