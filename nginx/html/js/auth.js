const Auth = {

    tokenKey: "admin_token",

    userKey: "admin_user",

    async login(username, password) {

        Utils.loading(true);

        try {

            const resp = await API.post(
                "/login",
                {

                    username,
                    password

                }
            );

            localStorage.setItem(
                this.tokenKey,
                resp.token
            );

            await this.loadUser();

            window.location.href = "/admin.html";

        }
        catch (e) {

            Utils.toast(
                e.detail || "Login failed",
                "danger"
            );

        }

        Utils.loading(false);

    },

    async loadUser() {

        try {

            const user = await API.get(
                "/me"
            );

            localStorage.setItem(
                this.userKey,
                JSON.stringify(user)
            );

            return user;

        }
        catch (e) {

            this.logout();

        }

    },

    user() {

        const u =
            localStorage.getItem(this.userKey);

        return u ? JSON.parse(u) : null;

    },

        token() {

        return localStorage.getItem(this.tokenKey);

    },

    logout() {

        localStorage.removeItem(this.tokenKey);

        localStorage.removeItem(this.userKey);

        window.location.href = "/login.html";

    },

    require(role = null) {

        const token = this.token();

        if (!token) {

            window.location.href = "/login.html";

            return;

        }

        const user = this.user();

        if (!user) {

            window.location.href = "/login.html";

            return;

        }

        if (role && user.role !== role) {

            Utils.toast(
                "Access denied",
                "danger"
            );

            window.location.href = "/login.html";

        }

    }
};