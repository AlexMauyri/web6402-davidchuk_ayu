import { apiRequest, clearCsrf, refreshCsrf } from "./api.js";
import { AuthFormData } from "./auth-form-data.js";

const form = document.querySelector("#auth-form");
const fields = document.querySelector("#auth-fields");
const panel = document.querySelector("#auth-panel");
const loginInput = document.querySelector("#login");
const passwordInput = document.querySelector("#password");
const rulesInput = document.querySelector("#rules");
const rulesField = document.querySelector("#rules-field");
const title = document.querySelector("#auth-title");
const description = document.querySelector("#auth-description");
const submitButton = document.querySelector("#submit-button");
const modeButton = document.querySelector("#mode-button");
const logoutButton = document.querySelector("#logout-button");
const retryButton = document.querySelector("#retry-button");
const status = document.querySelector("#auth-status");

let mode = "login";
let currentUser = null;
let ready = false;
let busy = false;

function showStatus(message, isError = false) {
    status.textContent = message;
    status.classList.toggle("auth__status--error", isError);
}

function render() {
    fields.disabled = !ready || busy;
    logoutButton.disabled = !ready || busy;
    logoutButton.hidden = !currentUser;
    panel.hidden = Boolean(currentUser);
    retryButton.hidden = ready || busy;
    form.setAttribute("aria-busy", String(busy));
    window.dispatchEvent(new CustomEvent("auth:state", {
        detail: { user: currentUser, busy: busy || !ready },
    }));
}

function setMode(nextMode) {
    mode = nextMode;
    const register = mode === "register";
    title.textContent = register ? "Регистрация" : "Вход";
    description.textContent = register
        ? "Создайте аккаунт, затем войдите с выбранными логином и паролем."
        : "Войдите, чтобы участвовать в обсуждениях.";
    submitButton.textContent = register ? "Зарегистрироваться" : "Войти";
    modeButton.textContent = register ? "Уже есть аккаунт - войти" : "Создать аккаунт";
    passwordInput.autocomplete = register ? "new-password" : "current-password";
    passwordInput.value = "";
    rulesInput.checked = false;
    rulesInput.required = register;
    rulesInput.disabled = !register;
    rulesField.hidden = !register;
    form.action = `/api/auth/${mode}`;
}

async function initialize() {
    busy = true;
    ready = false;
    showStatus("Проверяем состояние входа…");
    render();
    try {
        await refreshCsrf();
        try {
            currentUser = await apiRequest("/users/me");
        } catch (error) {
            if (error.status !== 401) {
                throw error;
            }
            currentUser = null;
        }
        ready = true;
        showStatus(currentUser ? "Вы уже вошли в аккаунт. Выйти можно кнопкой в шапке." : "");
        render();
    } catch {
        showStatus("Не удалось подключиться к API. Проверьте соединение и повторите подключение.", true);
    } finally {
        busy = false;
        render();
    }
}

async function renewToken() {
    clearCsrf();
    ready = false;
    await refreshCsrf();
    ready = true;
}

async function handleError(error) {
    if (error.code === "csrf_validation_failed") {
        try {
            await renewToken();
            showStatus("Защитный токен обновлён. Повторите действие; предыдущий запрос не выполнен.", true);
        } catch {
            showStatus("Не удалось обновить защитный токен. Повторите подключение.", true);
        }
        return;
    }

    if (error.status === 401 && error.code !== "invalid_credentials") {
        currentUser = null;
        render();
    }
    showStatus(error.message || "Не удалось выполнить запрос. Попробуйте снова.", true);
}

modeButton.addEventListener("click", () => {
    if (busy) return;
    setMode(mode === "login" ? "register" : "login");
    showStatus("");
    loginInput.focus();
});

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!ready || busy || !form.reportValidity()) return;

    const data = new AuthFormData(loginInput.value, passwordInput.value, rulesInput.checked);
    data.log();
    busy = true;
    showStatus(mode === "register" ? "Создаём аккаунт…" : "Выполняем вход…");
    render();

    let completed = false;
    try {
        const user = await apiRequest(`/auth/${mode}`, { method: "POST", body: data.toPayload() });
        completed = true;
        if (mode === "register") {
            setMode("login");
            showStatus("Аккаунт создан. Теперь введите пароль и войдите.");
        } else {
            currentUser = user;
            render();
            await renewToken();
            try {
                currentUser = await apiRequest("/users/me");
            } catch (error) {
                if (error.status !== 401) throw error;
                currentUser = null;
                render();
                showStatus("Браузер не сохранил сессию. Разрешите cookie.", true);
                return;
            }
            render();
            showStatus("Вход выполнен успешно. Вы можете перейти на форум через меню навигации.");
        }
    } catch (error) {
        if (completed) {
            ready = false;
            showStatus("Сервер принял вход, но не удалось завершить проверку сессии. Повторите подключение перед следующим действием.", true);
        } else {
            await handleError(error);
        }
    } finally {
        data.password = "";
        passwordInput.value = "";
        busy = false;
        render();
        if (completed && mode === "login" && !currentUser) passwordInput.focus();
    }
});

logoutButton.addEventListener("click", async () => {
    if (!ready || busy) return;
    busy = true;
    showStatus("Выходим из аккаунта…");
    render();

    let completed = false;
    try {
        await apiRequest("/auth/logout", { method: "POST" });
        completed = true;
        currentUser = null;
        form.reset();
        setMode("login");
        render();
        await renewToken();
        showStatus("Вы вышли из аккаунта.");
    } catch (error) {
        if (completed) {
            showStatus("Выход выполнен, но защитный токен не обновлён. Повторите подключение.", true);
        } else {
            await handleError(error);
        }
    } finally {
        busy = false;
        render();
    }
});

retryButton.addEventListener("click", initialize);
window.addEventListener("pageshow", (event) => {
    if (event.persisted && !busy) initialize();
});
initialize();
