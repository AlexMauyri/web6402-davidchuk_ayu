const API_PREFIX = "/api";

let csrfToken = null;
let csrfRequest = null;

export class ApiError extends Error {
    constructor(message, { status = 0, code = "request_failed", detail = null } = {}) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.code = code;
        this.detail = detail;
    }
}

function parseError(payload, status) {
    if (payload?.error) {
        return new ApiError(payload.error.message, {
            status,
            code: payload.error.code,
        });
    }

    if (Array.isArray(payload?.detail)) {
        const message = payload.detail
            .map((item) => item.msg || "Проверьте данные формы")
            .join("; ");
        return new ApiError(message, { status, code: "validation_error", detail: payload.detail });
    }

    if (typeof payload?.detail === "string") {
        return new ApiError(payload.detail, { status, code: "validation_error" });
    }

    return new ApiError("Сервер не вернул подробности ошибки", {
        status,
        code: "http_error",
    });
}

async function readPayload(response) {
    if (response.status === 204) {
        return null;
    }

    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
        return null;
    }

    try {
        return await response.json();
    } catch {
        return null;
    }
}

export async function refreshCsrf() {
    if (csrfRequest) {
        return csrfRequest;
    }

    csrfRequest = fetch(`${API_PREFIX}/auth/csrf`, {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
    })
        .then(async (response) => {
            const payload = await readPayload(response);
            if (!response.ok) {
                throw parseError(payload, response.status);
            }
            csrfToken = payload?.csrf_token || null;
            if (!csrfToken) {
                throw new ApiError("Сервер не вернул CSRF-токен", { code: "csrf_missing" });
            }
            return csrfToken;
        })
        .catch((error) => {
            csrfToken = null;
            if (error instanceof ApiError) {
                throw error;
            }
            throw new ApiError("Не удалось получить защитный токен. Проверьте соединение", {
                code: "network_error",
            });
        })
        .finally(() => {
            csrfRequest = null;
        });

    return csrfRequest;
}

export async function apiRequest(path, { method = "GET", body = undefined, headers = {} } = {}) {
    const isMutation = !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
    if (isMutation && !csrfToken) {
        await refreshCsrf();
    }

    const requestHeaders = {
        Accept: "application/json",
        ...headers,
    };

    const request = {
        method,
        credentials: "same-origin",
        cache: "no-store",
        headers: requestHeaders,
    };

    if (isMutation) {
        requestHeaders["X-CSRF-Token"] = csrfToken;
    }

    if (body !== undefined) {
        requestHeaders["Content-Type"] = "application/json";
        request.body = JSON.stringify(body);
    }

    let response;
    try {
        response = await fetch(`${API_PREFIX}${path}`, request);
    } catch {
        throw new ApiError(isMutation
            ? "Соединение прервано. Результат операции неизвестен: проверьте состояние перед повторной отправкой"
            : "Сервер недоступен. Проверьте соединение и попробуйте снова", {
            code: "network_error",
        });
    }

    const payload = await readPayload(response);
    if (!response.ok) {
        throw parseError(payload, response.status);
    }
    if (response.status !== 204 && payload === null) {
        throw new ApiError("Сервер вернул ответ в неожиданном формате. Проверьте состояние операции перед повторной отправкой", {
            status: response.status,
            code: "invalid_response",
        });
    }

    return payload;
}

export function clearCsrf() {
    csrfToken = null;
}
