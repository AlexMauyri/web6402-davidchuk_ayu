from fastapi import APIRouter, Depends

from app.api.dependencies import Actor, Users, require_csrf
from app.schemas import UserLoginUpdate, UserPasswordUpdate, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def me(service: Users, actor: Actor):
    return service.me(actor)


@router.put("/me/login", response_model=UserRead, dependencies=[Depends(require_csrf)])
async def update_login(data: UserLoginUpdate, service: Users, actor: Actor):
    return await service.update_login(data, actor)


@router.put("/me/password", status_code=204, dependencies=[Depends(require_csrf)])
async def update_password(data: UserPasswordUpdate, service: Users, actor: Actor):
    return await service.update_password(data, actor)


@router.delete("/me", status_code=204, dependencies=[Depends(require_csrf)])
async def delete(service: Users, actor: Actor):
    return await service.delete(actor)
