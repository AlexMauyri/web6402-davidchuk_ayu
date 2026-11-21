from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.db.sqlstate import FOREIGN_KEY_VIOLATION
from app.db.models import Comment
from app.schemas import CommentCreate, CommentRead, CommentUpdate, Page, UserRead
from app.services.common import check_owner, require_thread, transaction, validate_pagination
from app.services.exceptions import CommentNotFound, ThreadNotFound, UserNotFound


class CommentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _require(self, thread_id: int, comment_id: int) -> Comment:
        await require_thread(self.session, thread_id)
        comment = await crud.get_comment(self.session, comment_id, thread_id=thread_id)
        if comment is None:
            raise CommentNotFound()
        return comment

    async def list(
        self, thread_id: int, *, page: int = 1, page_size: int = 20,
    ) -> Page[CommentRead]:
        validate_pagination(page, page_size)
        await require_thread(self.session, thread_id)
        items, total = await crud.list_comments(
            self.session, thread_id=thread_id, page=page, page_size=page_size,
        )
        return Page[CommentRead](
            items=[CommentRead.model_validate(item) for item in items],
            total=total, page=page, page_size=page_size,
        )

    async def get(self, thread_id: int, comment_id: int) -> CommentRead:
        return CommentRead.model_validate(await self._require(thread_id, comment_id))

    async def create(self, thread_id: int, data: CommentCreate, actor: UserRead) -> CommentRead:
        async with transaction(self.session, conflicts={
            (FOREIGN_KEY_VIOLATION, "comments_thread_id_fkey"): ThreadNotFound,
            (FOREIGN_KEY_VIOLATION, "comments_user_id_fkey"): UserNotFound,
        }):
            await require_thread(self.session, thread_id)
            comment = await crud.create_comment(
                self.session, thread_id=thread_id, user_id=actor.id, text=data.text,
            )
            result = CommentRead.model_validate(comment)
        return result

    async def update(
        self, thread_id: int, comment_id: int, data: CommentUpdate, actor: UserRead,
    ) -> CommentRead:
        async with transaction(self.session):
            original = await self._require(thread_id, comment_id)
            check_owner(actor, original.user_id)
            comment = await crud.update_comment(
                self.session, comment_id, thread_id=thread_id, text=data.text,
            )
            if comment is None:
                raise CommentNotFound()
            result = CommentRead.model_validate(comment)
        return result

    async def delete(self, thread_id: int, comment_id: int, actor: UserRead) -> None:
        async with transaction(self.session):
            comment = await self._require(thread_id, comment_id)
            check_owner(actor, comment.user_id)
            if not await crud.delete_comment(self.session, comment_id, thread_id=thread_id):
                raise CommentNotFound()
