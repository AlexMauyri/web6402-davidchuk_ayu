import { apiRequest, clearCsrf, refreshCsrf } from "./api.js";

const loginLink = document.querySelector("#header-login");
const logoutButton = document.querySelector("#logout-button");
const userLabel = document.querySelector("#header-user");
const status = document.querySelector("#header-status");
const hasAuthForm = Boolean(document.querySelector("#auth-form"));

let currentUser = null;
let busy = false;
let sessionKnown = false;
let publicationBusy = false;

export function getHeaderSession() {
    return { user: currentUser, known: sessionKnown, busy };
}

function render(user, pending = false) {
    currentUser = user;
    loginLink.hidden = Boolean(user);
    userLabel.hidden = !user;
    userLabel.textContent = user ? user.login : "";
    logoutButton.hidden = !user;
    logoutButton.disabled = pending || publicationBusy;
    window.dispatchEvent(new CustomEvent("header:session", {
        detail: { user, known: sessionKnown, busy: pending },
    }));
}

async function loadSession() {
    if (busy || publicationBusy) return;
    busy = true;
    render(currentUser, true);
    status.textContent = "Проверяем сессию…";
    try {
        const user = await apiRequest("/users/me");
        sessionKnown = true;
        render(user);
        status.textContent = "";
    } catch (error) {
        if (error.status === 401) {
            sessionKnown = true;
            render(null);
            status.textContent = "";
        } else {
            status.textContent = "Не удалось проверить сессию. Обновите страницу, чтобы повторить.";
            render(currentUser);
        }
    } finally {
        busy = false;
    }
}

async function logout() {
    if (busy || publicationBusy) return;
    busy = true;
    render(currentUser, true);
    status.textContent = "Выходим из аккаунта…";
    let completed = false;
    try {
        await refreshCsrf();
        await apiRequest("/auth/logout", { method: "POST" });
        completed = true;
        clearCsrf();
        render(null);
        await refreshCsrf();
        status.textContent = "Вы вышли из аккаунта.";
    } catch (error) {
        if (completed) {
            status.textContent = "Выход выполнен. Не удалось обновить защитный токен; он будет запрошен при следующем действии.";
        } else if (error.code === "csrf_validation_failed") {
            clearCsrf();
            status.textContent = "Сессия изменилась в другой вкладке. Нажмите кнопку выхода ещё раз.";
        } else {
            status.textContent = error.message || "Не удалось выйти из аккаунта. Попробуйте снова.";
        }
    } finally {
        busy = false;
        render(currentUser);
    }
}

if (hasAuthForm) {
    window.addEventListener("auth:state", (event) => {
        render(event.detail.user, event.detail.busy);
    });
} else {
    window.addEventListener("forum:busy", (event) => {
        publicationBusy = event.detail;
        logoutButton.disabled = busy || publicationBusy;
    });
    window.addEventListener("auth:expired", () => {
        sessionKnown = true;
        render(null);
    });
    logoutButton.addEventListener("click", logout);
    window.addEventListener("pageshow", (event) => {
        if (event.persisted) loadSession();
    });
    window.addEventListener("focus", loadSession);
    loadSession();
}
