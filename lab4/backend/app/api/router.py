from fastapi import APIRouter

from app.api import auth, comments, threads, users
from app.schemas import ErrorResponse

router = APIRouter(prefix="/api", responses={
    status: {"model": ErrorResponse}
    for status in (401, 403, 404, 409, 500)
})
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(threads.router)
router.include_router(comments.router)
