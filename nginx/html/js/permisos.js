const Permissions = {

    clients: [],

    services: [],

    selectedClientId: null,

    async load() {

        Utils.loading(true);

        try {

            const [clients, services] = await Promise.all([

                API.get(API.managerUrl("/clients")),

                API.get(API.managerUrl("/services"))

            ]);

            this.clients = clients;

            this.services = services;

            this.render();

        }
        catch (e) {

            Utils.toast(
                e.detail || "Could not load permissions",
                "danger"
            );

        }

        Utils.loading(false);

    },

    async render() {

        const container =
            document.getElementById("permissionsContainer");

        container.innerHTML = "";

        const select = document.createElement("select");

        select.className = "form-select mb-3";

        select.innerHTML = `

            <option value="">Select client</option>

        `;

        this.clients.forEach(c => {

            select.innerHTML += `

                <option value="${c.id}">

                    ${c.name} (${c.email})

                </option>

            `;

        });

        select.onchange = async (e) => {

            this.selectedClientId = e.target.value;

            if (this.selectedClientId) {

                await this.renderMatrix();

            }

        };

        container.appendChild(select);

        const matrixDiv = document.createElement("div");

        matrixDiv.id = "permissionMatrix";

        container.appendChild(matrixDiv);

    },

        async renderMatrix() {

        const container =
            document.getElementById("permissionMatrix");

        container.innerHTML =
            "<p>Loading permissions...</p>";

        try {

            const granted = await API.get(

                API.managerUrl(
                    "/permissions/client/" + this.selectedClientId
                )

            );

            const grantedSet = new Set(
                granted.map(p => p.service_id)
            );

            let html = `

            <table class="table table-bordered">

                <thead class="table-dark">

                    <tr>

                        <th>Service</th>

                        <th>Method</th>

                        <th>Access</th>

                    </tr>

                </thead>

                <tbody>

            `;

            this.services.forEach(s => {

                const checked = grantedSet.has(s.id);

                html += `

                <tr>

                    <td>${s.name}</td>

                    <td>
                        <span class="badge bg-secondary">
                            ${s.method}
                        </span>
                    </td>

                    <td>

                        <input
                            type="checkbox"
                            onchange="Permissions.toggle(${s.id}, this.checked)"
                            ${checked ? "checked" : ""}
                        >

                    </td>

                </tr>

                `;

            });

            html += `

                </tbody>

            </table>

            `;

            container.innerHTML = html;

        }
        catch (e) {

            container.innerHTML =
                "<p>Error loading permissions</p>";

        }

    },

        async toggle(serviceId, enabled) {

        if (!this.selectedClientId) {

            Utils.toast(
                "Select a client first",
                "warning"
            );

            return;

        }

        try {

            if (enabled) {

                await API.post(
                    API.managerUrl("/permissions"),
                    {

                        client_id: parseInt(this.selectedClientId),

                        service_id: serviceId

                    }

                );

                Utils.toast(
                    "Permission granted",
                    "success"
                );

            }
            else {

                await API.delete(
                    API.managerUrl("/permissions"),
                    {

                        client_id: parseInt(this.selectedClientId),

                        service_id: serviceId

                    }

                );

                Utils.toast(
                    "Permission revoked",
                    "success"
                );

            }

        }
        catch (e) {

            Utils.toast(
                e.detail || "Error updating permission",
                "danger"
            );

        }

    },

    refresh() {

        this.load();

    }

};