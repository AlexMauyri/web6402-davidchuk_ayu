class ServiceError(Exception):
    code = "service_error"
    message = "Не удалось выполнить операцию"

    def __init__(self):
        super().__init__(self.message)


class AuthenticationRequired(ServiceError):
    code = "authentication_required"
    message = "Необходимо войти в систему"


class InvalidCredentials(ServiceError):
    code = "invalid_credentials"
    message = "Неверные учётные данные"


class SessionExpired(ServiceError):
    code = "session_expired"
    message = "Срок действия сессии истёк"


class PermissionDenied(ServiceError):
    code = "permission_denied"
    message = "Недостаточно прав"


class CsrfValidationFailed(ServiceError):
    code = "csrf_validation_failed"
    message = "Неверный CSRF-токен"


class UserNotFound(ServiceError):
    code = "user_not_found"
    message = "Пользователь не найден"


class ThreadNotFound(ServiceError):
    code = "thread_not_found"
    message = "Тред не найден"


class CommentNotFound(ServiceError):
    code = "comment_not_found"
    message = "Комментарий не найден"


class LoginAlreadyExists(ServiceError):
    code = "login_already_exists"
    message = "Логин уже занят"


class AccountHasContent(ServiceError):
    code = "account_has_content"
    message = "Нельзя удалить аккаунт с публикациями"


class InvalidPagination(ServiceError):
    code = "invalid_pagination"
    message = "Некорректные параметры страницы"
