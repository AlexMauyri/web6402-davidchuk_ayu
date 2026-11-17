from fastapi import APIRouter, Depends

from app.api.dependencies import Auth, require_csrf
from app.schemas import CsrfRead, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/csrf", response_model=CsrfRead)
async def csrf(auth: Auth):
    return auth.csrf()


@router.post("/register", response_model=UserRead, status_code=201, dependencies=[Depends(require_csrf)])
async def register(data: UserCreate, auth: Auth):
    return await auth.register(data)


@router.post("/login", response_model=UserRead, dependencies=[Depends(require_csrf)])
async def login(data: UserLogin, auth: Auth):
    return await auth.login(data)


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf)])
async def logout(auth: Auth):
    return auth.logout()
