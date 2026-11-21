import { apiRequest, clearCsrf, refreshCsrf } from "./api.js";
import { getHeaderSession } from "./header-auth.js";

const title = document.querySelector("#forum-title");
const description = document.querySelector("#forum-description");
const status = document.querySelector("#forum-status");
const retryButton = document.querySelector("#forum-retry");
const backLink = document.querySelector("#threads-link");
const threadsPanel = document.querySelector("#threads-panel");
const threadPanel = document.querySelector("#thread-panel");
const threadList = document.querySelector("#thread-list");
const threadContent = document.querySelector("#thread-content");
const commentList = document.querySelector("#comment-list");
const commentsStatus = document.querySelector("#comments-status");
const threadsPagination = document.querySelector("#threads-pagination");
const commentsPagination = document.querySelector("#comments-pagination");
const dateFormat = new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" });

let loadVersion = 0;
let context = null;
let session = getHeaderSession();
let mutating = false;
let loading = true;
let editing = null;
const actions = document.querySelector("#forum-actions");
const accountStatus = document.querySelector("#forum-account-status");
const editor = document.querySelector("#editor-panel");
const editorTitle = document.querySelector("#editor-title");
const postForm = document.querySelector("#post-form");
const postFields = document.querySelector("#post-fields");
const postTitleField = document.querySelector("#post-title-field");
const postTitle = document.querySelector("#post-title");
const postText = document.querySelector("#post-text");
const postSubmit = document.querySelector("#post-submit");
const postCancel = document.querySelector("#post-cancel");

function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
}

function positiveInteger(params, key, fallback) {
    const values = params.getAll(key);
    if (!values.length) return fallback;
    const value = values[0];
    if (values.length !== 1 || !/^[1-9]\d*$/.test(value) || !Number.isSafeInteger(Number(value))) {
        throw new Error("Некорректный адрес страницы. Откройте форум через пункт навигации.");
    }
    return Number(value);
}

function forumUrl({ page = 1, threadId = null, commentsPage = 1 } = {}) {
    const params = new URLSearchParams();
    if (page !== 1) params.set("page", page);
    if (threadId !== null) params.set("thread_id", threadId);
    if (threadId !== null && commentsPage !== 1) params.set("comments_page", commentsPage);
    return `forum.html${params.size ? `?${params}` : ""}`;
}

function metadata(author, createdAt) {
    const node = element("p", undefined, "forum__meta");
    node.append(document.createTextNode(`${author} · `));
    const date = new Date(createdAt);
    if (Number.isNaN(date.getTime())) {
        node.append(document.createTextNode("Дата неизвестна"));
    } else {
        const time = element("time", dateFormat.format(date));
        time.dateTime = date.toISOString();
        node.append(time);
    }
    return node;
}

function pagination(container, data, urlForPage) {
    container.replaceChildren();
    if (data.total_pages < 2) return;
    function addLink(label, page, rel) {
        const link = element("a", label);
        link.href = urlForPage(page);
        link.rel = rel;
        container.append(link);
    }
    if (data.page > 1) addLink("Предыдущая", data.page - 1, "prev");
    container.append(element("span", `Страница ${data.page} из ${data.total_pages}`));
    if (data.page < data.total_pages) addLink("Следующая", data.page + 1, "next");
}

function showStatus(message, isError = false) {
    status.textContent = message;
    status.classList.toggle("forum__status--error", isError);
}

async function loadThreads(page, version) {
    const data = await apiRequest(`/threads?page=${page}&page_size=20`);
    if (version !== loadVersion) return;
    context.listReady = true;
    threadsPanel.hidden = false;
    if (page > Math.max(1, data.total_pages)) {
        showStatus("На этой странице тем нет. Перейдите к доступным страницам.");
        const link = element("a", "К последней странице тем");
        link.href = forumUrl({ page: Math.max(1, data.total_pages) });
        threadsPagination.append(link);
        return;
    }
    for (const thread of data.items) {
        const item = element("li", undefined, "forum__thread");
        const heading = element("h2");
        const link = element("a", thread.title);
        link.href = forumUrl({ page, threadId: thread.id });
        heading.append(link);
        item.append(heading, metadata(thread.author.login, thread.created_at));
        threadList.append(item);
    }
    pagination(threadsPagination, data, (nextPage) => forumUrl({ page: nextPage }));
    showStatus(data.total ? `Всего тем: ${data.total}.` : "Тем пока нет.");
}

async function loadThread(threadId, page, commentsPage, version) {
    const thread = await apiRequest(`/threads/${threadId}`);
    if (version !== loadVersion) return;
    context.thread = thread;
    title.textContent = thread.title;
    document.title = `${thread.title} // Форум TempleOS`;
    description.hidden = true;
    threadContent.append(
        metadata(thread.author.login, thread.created_at),
        element("p", thread.text, "forum__text"),
    );
    threadPanel.hidden = false;
    showStatus("");
    commentsStatus.textContent = "Загружаем комментарии…";

    const data = await apiRequest(`/threads/${threadId}/comments?page=${commentsPage}&page_size=20`);
    if (version !== loadVersion) return;
    if (commentsPage > Math.max(1, data.total_pages)) {
        commentsStatus.textContent = "На этой странице комментариев нет.";
        const link = element("a", "К последней странице комментариев");
        link.href = forumUrl({ page, threadId, commentsPage: Math.max(1, data.total_pages) });
        commentsPagination.append(link);
        return;
    }
    context.comments = data.items;
    for (const comment of data.items) {
        const item = element("li", undefined, "forum__comment");
        item.id = `comment-${comment.id}`;
        item.append(
            metadata(comment.author.login, comment.created_at),
            element("p", comment.text, "forum__text"),
        );
        commentList.append(item);
    }
    commentsStatus.textContent = data.total ? `Всего комментариев: ${data.total}.` : "Комментариев пока нет.";
    pagination(commentsPagination, data, (nextPage) => forumUrl({ page, threadId, commentsPage: nextPage }));
}

async function loadForum() {
    const version = ++loadVersion;
    loading = true;
    context = null;
    renderManagement();
    retryButton.hidden = true;
    threadsPanel.hidden = true;
    threadPanel.hidden = true;
    backLink.hidden = true;
    description.hidden = false;
    title.textContent = "Форум TempleOS";
    document.title = "TempleOS // Форум";
    for (const node of [threadList, threadContent, commentList, threadsPagination, commentsPagination]) {
        node.replaceChildren();
    }
    commentsStatus.textContent = "";
    showStatus("Загружаем обсуждения…");
    try {
        const params = new URLSearchParams(window.location.search);
        const page = positiveInteger(params, "page", 1);
        const threadId = positiveInteger(params, "thread_id", null);
        const commentsPage = positiveInteger(params, "comments_page", 1);
        context = { page, threadId, commentsPage, thread: null, comments: [], listReady: false };
        if (threadId === null) {
            await loadThreads(page, version);
        } else {
            backLink.href = forumUrl({ page });
            backLink.hidden = false;
            await loadThread(threadId, page, commentsPage, version);
        }
    } catch (error) {
        if (version !== loadVersion) return;
        commentsStatus.textContent = "";
        if (error.code === "thread_not_found" || error.status === 404) {
            context = null;
            threadPanel.hidden = true;
            showStatus("Тема не найдена. Возможно, она была удалена. Вернитесь к списку тем.", true);
        } else {
            showStatus(error.message || "Не удалось загрузить обсуждения.", true);
            retryButton.hidden = false;
        }
    } finally {
        if (version === loadVersion) {
            loading = false;
            renderManagement();
        }
    }
}

function setMutating(value) {
    mutating = value;
    window.dispatchEvent(new CustomEvent("forum:busy", { detail: value }));
}

function canManage(ownerId) {
    return session.known && session.user
        && (session.user.id === ownerId || session.user.role === "moderator");
}

function canSubmit() {
    if (!session.known || !session.user || session.busy || loading || mutating) return false;
    return !editing?.record || canManage(editing.ownerId);
}

function actionButton(label, handler) {
    const button = element("button", label, "forum__button");
    button.type = "button";
    button.disabled = loading || mutating || session.busy;
    button.addEventListener("click", handler);
    return button;
}

function renderManagement() {
    actions.replaceChildren();
    document.querySelectorAll(".forum__record-actions").forEach((node) => node.remove());
    retryButton.disabled = mutating;
    postFields.disabled = mutating;
    postSubmit.disabled = !canSubmit();
    if (!session.known) {
        accountStatus.textContent = "Состояние входа не подтверждено. Если проверка не завершится, обновите страницу.";
    } else if (!session.user) {
        accountStatus.replaceChildren(document.createTextNode("Для публикации "));
        const link = element("a", "войдите в аккаунт в новой вкладке");
        link.href = "auth.html";
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        accountStatus.append(link, document.createTextNode(". Введённый здесь текст останется в форме."));
    } else {
        accountStatus.textContent = "";
    }
    if (!context || !session.known || !session.user || loading) return;
    if (context.thread) {
        actions.append(actionButton("Написать комментарий", () => openEditor("comment")));
        addRecordActions(threadContent, "thread", context.thread, context.thread.created_by);
        for (const comment of context.comments) {
            const node = document.getElementById(`comment-${comment.id}`);
            if (node) addRecordActions(node, "comment", comment, comment.user_id);
        }
    } else if (context.listReady) {
        actions.append(actionButton("Создать тему", () => openEditor("thread")));
    }
}

function addRecordActions(node, kind, record, ownerId) {
    if (!canManage(ownerId)) return;
    const controls = element("div", undefined, "forum__actions forum__record-actions");
    controls.append(
        actionButton("Редактировать", () => openEditor(kind, record, ownerId)),
        actionButton("Удалить", () => deleteRecord(kind, record)),
    );
    node.append(controls);
}

function hasDraft() {
    return editing && (postTitle.value !== editing.initialTitle || postText.value !== editing.initialText);
}

function closeEditor() {
    if (mutating) return;
    if (hasDraft() && !window.confirm("Отменить изменения? Введённый текст будет потерян.")) return;
    editing = null;
    editor.hidden = true;
    postForm.reset();
    actions.querySelector("button")?.focus();
}

function openEditor(kind, record = null, ownerId = null) {
    if (loading || mutating || !session.user) return;
    if (record && !canManage(ownerId)) return;
    if (hasDraft() && !window.confirm("Открыть другую форму? Несохранённый текст будет потерян.")) return;
    editing = {
        kind, record, ownerId,
        threadId: context.threadId,
        initialTitle: record?.title || "",
        initialText: record?.text || "",
    };
    const isThread = kind === "thread";
    editorTitle.textContent = record
        ? (isThread ? "Редактирование темы" : "Редактирование комментария")
        : (isThread ? "Новая тема" : "Новый комментарий");
    postTitleField.hidden = !isThread;
    postTitle.disabled = !isThread;
    postTitle.required = isThread;
    postTitle.value = editing.initialTitle;
    postText.value = editing.initialText;
    postSubmit.textContent = record ? "Сохранить изменения" : "Опубликовать";
    editor.hidden = false;
    renderManagement();
    (isThread ? postTitle : postText).focus();
    editor.scrollIntoView({ block: "nearest" });
}

async function mutationError(error) {
    if (error.status === 401) {
        window.dispatchEvent(new Event("auth:expired"));
        showStatus("Сессия истекла. Войдите в новой вкладке, затем вернитесь и повторите отправку. Текст сохранён в форме.", true);
    } else if (error.code === "csrf_validation_failed") {
        clearCsrf();
        try {
            await refreshCsrf();
            showStatus("Защитный токен обновлён. Повторите действие вручную; текст сохранён в форме.", true);
        } catch {
            showStatus("Не удалось обновить защитный токен. Проверьте соединение и повторите действие позже.", true);
        }
    } else {
        showStatus(error.message || "Не удалось выполнить действие. Текст сохранён в форме.", true);
    }
}

postForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!editing || !canSubmit() || !postForm.reportValidity()) return;
    if (!postText.value.trim() || (editing.kind === "thread" && !postTitle.value.trim())) {
        showStatus("Заголовок и текст не должны состоять только из пробелов.", true);
        return;
    }
    const draft = editing;
    const path = draft.kind === "thread"
        ? `/threads${draft.record ? `/${draft.record.id}` : ""}`
        : `/threads/${draft.threadId}/comments${draft.record ? `/${draft.record.id}` : ""}`;
    const body = draft.kind === "thread"
        ? { title: postTitle.value, text: postText.value }
        : { text: postText.value };
    setMutating(true);
    renderManagement();
    showStatus("Сохраняем публикацию…");
    try {
        const result = await apiRequest(path, { method: draft.record ? "PUT" : "POST", body });
        editing = null;
        editor.hidden = true;
        postForm.reset();
        if (draft.kind === "thread" && !draft.record) {
            window.location.assign(forumUrl({ threadId: result.id }));
            return;
        }
        if (draft.kind === "comment" && !draft.record) {
            const data = await apiRequest(`/threads/${draft.threadId}/comments?page=1&page_size=20`);
            const url = forumUrl({ ...context, commentsPage: Math.max(1, data.total_pages) });
            window.history.replaceState(null, "", url);
        }
        await loadForum();
    } catch (error) {
        if (!editing) {
            showStatus("Публикация сохранена, но не удалось обновить обсуждение. Обновите страницу; повторно отправлять публикацию не нужно.", true);
            retryButton.hidden = false;
        } else {
            await mutationError(error);
        }
    } finally {
        setMutating(false);
        renderManagement();
    }
});

async function deleteRecord(kind, record) {
    if (loading || mutating || session.busy) return;
    const question = kind === "thread"
        ? "Удалить тему и все её комментарии? Это действие нельзя отменить."
        : "Удалить комментарий? Это действие нельзя отменить.";
    if (!window.confirm(question + (hasDraft() ? " Несохранённый текст в форме будет потерян." : ""))) return;
    const path = kind === "thread"
        ? `/threads/${record.id}`
        : `/threads/${context.threadId}/comments/${record.id}`;
    setMutating(true);
    renderManagement();
    showStatus("Удаляем публикацию…");
    let deleted = false;
    try {
        await apiRequest(path, { method: "DELETE" });
        deleted = true;
        editing = null;
        editor.hidden = true;
        postForm.reset();
        if (kind === "thread") {
            window.location.assign(forumUrl({ page: context.page }));
            return;
        }
        const data = await apiRequest(`/threads/${context.threadId}/comments?page=1&page_size=20`);
        window.history.replaceState(null, "", forumUrl({
            ...context, commentsPage: Math.min(context.commentsPage, Math.max(1, data.total_pages)),
        }));
        await loadForum();
    } catch (error) {
        if (deleted) {
            showStatus("Публикация удалена, но не удалось обновить обсуждение. Обновите страницу.", true);
            retryButton.hidden = false;
        } else {
            await mutationError(error);
        }
    } finally {
        setMutating(false);
        renderManagement();
    }
}

postCancel.addEventListener("click", closeEditor);
window.addEventListener("header:session", (event) => {
    session = event.detail;
    renderManagement();
});
window.addEventListener("beforeunload", (event) => {
    if (!hasDraft()) return;
    event.preventDefault();
    event.returnValue = "";
});

retryButton.addEventListener("click", () => {
    if (!mutating) loadForum();
});
window.addEventListener("pageshow", (event) => {
    if (event.persisted && !editing && !mutating) loadForum();
});
loadForum();
