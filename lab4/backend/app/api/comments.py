from fastapi import APIRouter, Depends

from app.api.dependencies import Actor, Comments, EntityId, PageNumber, PageSize, require_csrf
from app.schemas import CommentCreate, CommentRead, CommentUpdate, Page

router = APIRouter(prefix="/threads/{thread_id}/comments", tags=["comments"])


@router.get("", response_model=Page[CommentRead])
async def list_comments(
    thread_id: EntityId, service: Comments, page: PageNumber = 1, page_size: PageSize = 20,
):
    return await service.list(thread_id, page=page, page_size=page_size)


@router.get("/{comment_id}", response_model=CommentRead)
async def get_comment(thread_id: EntityId, comment_id: EntityId, service: Comments):
    return await service.get(thread_id, comment_id)


@router.post("", response_model=CommentRead, status_code=201, dependencies=[Depends(require_csrf)])
async def create_comment(thread_id: EntityId, data: CommentCreate, service: Comments, actor: Actor):
    return await service.create(thread_id, data, actor)


@router.put("/{comment_id}", response_model=CommentRead, dependencies=[Depends(require_csrf)])
async def update_comment(
    thread_id: EntityId, comment_id: EntityId, data: CommentUpdate, service: Comments, actor: Actor,
):
    return await service.update(thread_id, comment_id, data, actor)


@router.delete("/{comment_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_comment(thread_id: EntityId, comment_id: EntityId, service: Comments, actor: Actor):
    return await service.delete(thread_id, comment_id, actor)
