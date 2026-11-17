from collections.abc import MutableMapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.db.sqlstate import FOREIGN_KEY_VIOLATION, UNIQUE_VIOLATION
from app.schemas import UserLoginUpdate, UserPasswordUpdate, UserRead
from app.services.common import transaction
from app.services.exceptions import AccountHasContent, InvalidCredentials, LoginAlreadyExists, UserNotFound
from app.services.security import hash_password, verify_password


class UserService:
    def __init__(self, session: AsyncSession, client_session: MutableMapping[str, Any]):
        self.session = session
        self.client_session = client_session

    def me(self, actor: UserRead) -> UserRead:
        return actor

    async def update_login(self, data: UserLoginUpdate, actor: UserRead) -> UserRead:
        async with transaction(
            self.session, conflicts={(UNIQUE_VIOLATION, "ix_users_login"): LoginAlreadyExists},
        ):
            user = await crud.update_user_login(self.session, actor.id, login=data.login)
            if user is None:
                raise UserNotFound()
            result = UserRead.model_validate(user)
        return result

    async def update_password(self, data: UserPasswordUpdate, actor: UserRead) -> None:
        async with transaction(self.session):
            user = await crud.get_user(self.session, actor.id)
            if user is None:
                raise UserNotFound()
            if not await verify_password(user.password_hash, data.current_password.get_secret_value()):
                raise InvalidCredentials()
            password_hash = await hash_password(data.new_password.get_secret_value())
            updated = await crud.update_user_password_hash(self.session, actor.id, password_hash=password_hash)
            if updated is None:
                raise UserNotFound()

    async def delete(self, actor: UserRead) -> None:
        async with transaction(self.session, conflicts={
            (FOREIGN_KEY_VIOLATION, "threads_created_by_fkey"): AccountHasContent,
            (FOREIGN_KEY_VIOLATION, "comments_user_id_fkey"): AccountHasContent,
        }):
            if not await crud.delete_user(self.session, actor.id):
                raise UserNotFound()
        self.client_session.clear()
