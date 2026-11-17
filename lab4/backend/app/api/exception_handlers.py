import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.services import exceptions as errors

logger = logging.getLogger(__name__)

_STATUS = {
    errors.AuthenticationRequired: 401,
    errors.InvalidCredentials: 401,
    errors.SessionExpired: 401,
    errors.PermissionDenied: 403,
    errors.CsrfValidationFailed: 403,
    errors.UserNotFound: 404,
    errors.ThreadNotFound: 404,
    errors.CommentNotFound: 404,
    errors.LoginAlreadyExists: 409,
    errors.AccountHasContent: 409,
    errors.InvalidPagination: 422,
}


async def service_error_handler(request: Request, error: errors.ServiceError) -> JSONResponse:
    status = _STATUS.get(type(error), 500)
    return JSONResponse(
        status_code=status,
        content={"error": {"code": error.code, "message": error.message}},
    )


async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={
        "detail": [
            {"loc": item["loc"], "type": item["type"], "msg": item["msg"]}
            for item in error.errors()
        ],
    })


async def internal_error_handler(request: Request, error: Exception) -> JSONResponse:
    logger.error("Внутренняя ошибка запроса: %s", type(error).__name__)
    return JSONResponse(status_code=500, content={
        "error": {"code": "internal_error", "message": "Внутренняя ошибка сервера"},
    })


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(errors.ServiceError, service_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, internal_error_handler)
