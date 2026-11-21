from fastapi import APIRouter, Depends

from app.api.dependencies import Actor, EntityId, PageNumber, PageSize, Threads, require_csrf
from app.schemas import Page, ThreadCreate, ThreadListItem, ThreadRead, ThreadUpdate

router = APIRouter(prefix="/threads", tags=["threads"])


@router.get("", response_model=Page[ThreadListItem])
async def list_threads(service: Threads, page: PageNumber = 1, page_size: PageSize = 20):
    return await service.list(page=page, page_size=page_size)


@router.get("/{thread_id}", response_model=ThreadRead)
async def get_thread(thread_id: EntityId, service: Threads):
    return await service.get(thread_id)


@router.post("", response_model=ThreadRead, status_code=201, dependencies=[Depends(require_csrf)])
async def create_thread(data: ThreadCreate, service: Threads, actor: Actor):
    return await service.create(data, actor)


@router.put("/{thread_id}", response_model=ThreadRead, dependencies=[Depends(require_csrf)])
async def update_thread(thread_id: EntityId, data: ThreadUpdate, service: Threads, actor: Actor):
    return await service.update(thread_id, data, actor)


@router.delete("/{thread_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_thread(thread_id: EntityId, service: Threads, actor: Actor):
    return await service.delete(thread_id, actor)
