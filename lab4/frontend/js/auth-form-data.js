export class AuthFormData {
    constructor(login, password, rulesAccepted) {
        this.login = login;
        this.password = password;
        this.rulesAccepted = rulesAccepted;
    }

    log() {
        console.group("Данные формы авторизации");
        console.table({
            login: this.login,
            password: "[скрыт]",
            rulesAccepted: this.rulesAccepted,
        });
        console.groupEnd();
    }

    toPayload() {
        return { login: this.login, password: this.password };
    }
}
