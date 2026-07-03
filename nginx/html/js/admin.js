Auth.require("admin");

const Dashboard = {

    currentSection: "dashboard",

    async init() {

        const user = Auth.user();

        if (user) {

            document.getElementById("adminName").innerHTML =
                user.username ?? "Administrator";

        }

        this.showSection("dashboard");

        await this.loadDashboard();

        await Clients.load();

        await Services.load();

        await Permissions.load();

    },

    showSection(section) {

        const sections = [

            "dashboard",
            "clients",
            "services",
            "permissions",
            "metrics"

        ];

        sections.forEach(name => {

            document
                .getElementById(name + "Section")
                .classList.add("d-none");

        });

        document
            .getElementById(section + "Section")
            .classList.remove("d-none");

        this.currentSection = section;

    },

    async loadDashboard() {

        Utils.loading(true);

        try {

            const stats = await API.get("/stats/overview");

            document.getElementById("activeClients").innerHTML =
                stats.active_clients;

            document.getElementById("activeServices").innerHTML =
                stats.active_services;

            document.getElementById("requests24").innerHTML =
                stats.requests_last_24h;

            document.getElementById("avgResponse").innerHTML =
                stats.avg_response_time_ms + " ms";

            if (typeof Charts !== "undefined") {

                await Charts.load();

            }

        }
        catch (e) {

            Utils.toast(
                "Dashboard could not be loaded",
                "danger"
            );

        }

        Utils.loading(false);

    },

    refresh() {

        switch (this.currentSection) {

            case "dashboard":

                this.loadDashboard();

                break;

            case "clients":

                Clients.load();

                break;

            case "services":

                Services.load();

                break;

            case "permissions":

                Permissions.load();

                break;

            case "metrics":

                if (typeof Charts !== "undefined") {

                    Charts.load();

                }

                break;

        }

    }

};

window.addEventListener(

    "load",

    () => Dashboard.init()

);