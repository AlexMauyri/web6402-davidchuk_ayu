from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.db.sqlstate import FOREIGN_KEY_VIOLATION
from app.schemas import Page, ThreadCreate, ThreadListItem, ThreadRead, ThreadUpdate, UserRead
from app.services.common import check_owner, require_thread, transaction, validate_pagination
from app.services.exceptions import ThreadNotFound, UserNotFound


class ThreadService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, *, page: int = 1, page_size: int = 20) -> Page[ThreadListItem]:
        validate_pagination(page, page_size)
        items, total = await crud.list_threads(self.session, page=page, page_size=page_size)
        return Page[ThreadListItem](
            items=[ThreadListItem.model_validate(item) for item in items],
            total=total, page=page, page_size=page_size,
        )

    async def get(self, thread_id: int) -> ThreadRead:
        return ThreadRead.model_validate(await require_thread(self.session, thread_id))

    async def create(self, data: ThreadCreate, actor: UserRead) -> ThreadRead:
        async with transaction(
            self.session, conflicts={(FOREIGN_KEY_VIOLATION, "threads_created_by_fkey"): UserNotFound},
        ):
            thread = await crud.create_thread(
                self.session, title=data.title, text=data.text, created_by=actor.id,
            )
            result = ThreadRead.model_validate(thread)
        return result

    async def update(self, thread_id: int, data: ThreadUpdate, actor: UserRead) -> ThreadRead:
        async with transaction(self.session):
            original = await require_thread(self.session, thread_id)
            check_owner(actor, original.created_by)
            thread = await crud.update_thread(self.session, thread_id, title=data.title, text=data.text)
            if thread is None:
                raise ThreadNotFound()
            result = ThreadRead.model_validate(thread)
        return result

    async def delete(self, thread_id: int, actor: UserRead) -> None:
        async with transaction(self.session):
            thread = await require_thread(self.session, thread_id)
            check_owner(actor, thread.created_by)
            if not await crud.delete_thread(self.session, thread_id):
                raise ThreadNotFound()
