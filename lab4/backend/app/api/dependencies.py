from typing import Annotated

from fastapi import Depends, Header, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas import UserRead
from app.services.auth import AuthService
from app.services.comments import CommentService
from app.services.threads import ThreadService
from app.services.users import UserService

Session = Annotated[AsyncSession, Depends(get_session)]
EntityId = Annotated[int, Path(gt=0)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def get_auth_service(request: Request, session: Session) -> AuthService:
    return AuthService(session, request.session, ttl=request.app.state.session_ttl)


Auth = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(auth: Auth) -> UserRead:
    return await auth.current_user()


async def require_csrf(
    auth: Auth, token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    auth.validate_csrf(token)


def get_user_service(request: Request, session: Session) -> UserService:
    return UserService(session, request.session)


def get_thread_service(session: Session) -> ThreadService:
    return ThreadService(session)


def get_comment_service(session: Session) -> CommentService:
    return CommentService(session)


Actor = Annotated[UserRead, Depends(get_current_user)]
Users = Annotated[UserService, Depends(get_user_service)]
Threads = Annotated[ThreadService, Depends(get_thread_service)]
Comments = Annotated[CommentService, Depends(get_comment_service)]
