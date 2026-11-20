from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.db.models import Thread
from app.schemas import UserRead
from app.services.exceptions import (
    InvalidPagination, PermissionDenied, ServiceError, ThreadNotFound,
)


def constraint_details(error: IntegrityError) -> tuple[str | None, str | None]:
    current = error.orig
    state = None
    constraint = None
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        state = state or getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        constraint = constraint or getattr(current, "constraint_name", None)
        current = getattr(current, "__cause__", None)
    return state, constraint


@asynccontextmanager
async def transaction(
    session: AsyncSession,
    *,
    conflicts: Mapping[tuple[str, str], type[ServiceError]] | None = None,
) -> AsyncGenerator[None]:
    try:
        yield
        await session.commit()
    except BaseException as error:
        await session.rollback()
        if isinstance(error, IntegrityError) and conflicts:
            mapped = conflicts.get(constraint_details(error))
            if mapped is not None:
                raise mapped() from error
        raise


def check_owner(actor: UserRead, owner_id: int) -> None:
    if actor.id != owner_id and actor.role != "moderator":
        raise PermissionDenied()


def validate_pagination(page: int, page_size: int) -> None:
    if type(page) is not int or page < 1:
        raise InvalidPagination()
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise InvalidPagination()


async def require_thread(session: AsyncSession, thread_id: int) -> Thread:
    thread = await crud.get_thread(session, thread_id)
    if thread is None:
        raise ThreadNotFound()
    return thread
