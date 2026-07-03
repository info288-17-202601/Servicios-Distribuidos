const Clients = {

    list: [],

    selectedId: null,

    modal: null,

    async load() {

        Utils.loading(true);

        try {

            this.list = await API.get(
                API.managerUrl("/clients")
            );

            this.renderTable();

        }
        catch (e) {

            Utils.toast(
                e.detail || "Could not load clients",
                "danger"
            );

        }

        Utils.loading(false);

    },

    renderTable() {

        const tbody =
            document.getElementById("clientsTable");

        tbody.innerHTML = "";

        this.list.forEach(client => {

            tbody.innerHTML += `

            <tr>

                <td>

                    ${client.id}

                </td>

                <td>

                    ${client.name}

                </td>

                <td>

                    ${client.email}

                </td>

                <td>

                    <code>

                        ${client.api_key}

                    </code>

                </td>

                <td>

                    ${client.is_active
                        ? '<span class="badge bg-success">Active</span>'
                        : '<span class="badge bg-danger">Disabled</span>'
                    }

                </td>

                <td>

                    <button
                        class="btn btn-sm btn-primary"

                        onclick="Clients.edit(${client.id})">

                        Edit

                    </button>

                    <button
                        class="btn btn-sm btn-warning"

                        onclick="Clients.toggle(${client.id})">

                        Toggle

                    </button>

                    <button
                        class="btn btn-sm btn-danger"

                        onclick="Clients.remove(${client.id})">

                        Delete

                    </button>

                </td>

            </tr>

            `;

        });

    },

    newClient() {

        this.selectedId = null;

        this.showForm({

            name: "",

            email: "",

            api_key: "",

            machine_id: ""

        });

    },

    async edit(id) {

        Utils.loading(true);

        try {

            const client =
                await API.get(

                    API.managerUrl("/clients/" + id)

                );

            this.selectedId = id;

            this.showForm(client);

            bootstrap.Modal
                .getOrCreateInstance(

                    document.getElementById(
                        "clientModal"
                    )

                )
                .show();

        }
        catch (e) {

            Utils.toast(

                e.detail || "Client not found",

                "danger"

            );

        }

        Utils.loading(false);

    },

    showForm(client) {

        const div =
            document.getElementById("clientForm");

        div.innerHTML = `

        <div class="mb-3">

            <label class="form-label">

                Name

            </label>

            <input

                id="clientName"

                class="form-control"

                value="${client.name}"

            >

        </div>

        <div class="mb-3">

            <label class="form-label">

                Email

            </label>

            <input

                id="clientEmail"

                class="form-control"

                value="${client.email}"

            >

        </div>

        <div class="mb-3">

            <label class="form-label">

                API Key

            </label>

            <input

                id="clientApi"

                class="form-control"

                value="${client.api_key}"

            >

        </div>

        <div class="mb-3">

            <label class="form-label">

                Machine ID

            </label>

            <input

                id="clientMachine"

                class="form-control"

                value="${client.machine_id ?? ""}"

            >

        </div>

        <div class="text-end">

            <button

                class="btn btn-secondary"

                data-bs-dismiss="modal">

                Cancel

            </button>

            <button

                class="btn btn-primary"

                onclick="Clients.save()">

                Save

            </button>

        </div>

        `;

    },

        async save() {

        const payload = {

            name: document.getElementById("clientName").value.trim(),

            email: document.getElementById("clientEmail").value.trim(),

            api_key: document.getElementById("clientApi").value.trim(),

            machine_id: document.getElementById("clientMachine").value.trim()

        };

        if (!payload.name || !payload.email || !payload.api_key) {

            Utils.toast(
                "Missing required fields",
                "warning"
            );

            return;

        }

        Utils.loading(true);

        try {

            if (this.selectedId) {

                await API.put(
                    API.managerUrl("/clients/" + this.selectedId),
                    payload
                );

                Utils.toast(
                    "Client updated",
                    "success"
                );

            }
            else {

                await API.post(
                    API.managerUrl("/clients"),
                    payload
                );

                Utils.toast(
                    "Client created",
                    "success"
                );

            }

            bootstrap.Modal
                .getInstance(
                    document.getElementById("clientModal")
                )
                .hide();

            await this.load();

            Dashboard.refresh();

        }
        catch (e) {

            Utils.toast(
                e.detail || "Error saving client",
                "danger"
            );

        }

        Utils.loading(false);

    },

    async toggle(id) {

        try {

            await API.patch(
                API.managerUrl("/clients/" + id + "/toggle")
            );

            Utils.toast(
                "Client status updated",
                "success"
            );

            await this.load();

            Dashboard.refresh();

        }
        catch (e) {

            Utils.toast(
                e.detail || "Error toggling client",
                "danger"
            );

        }

    },

    async remove(id) {

        if (!confirm("Delete this client?")) {

            return;

        }

        Utils.loading(true);

        try {

            await API.delete(
                API.managerUrl("/clients/" + id)
            );

            Utils.toast(
                "Client removed",
                "success"
            );

            await this.load();

            Dashboard.refresh();

        }
        catch (e) {

            Utils.toast(
                e.detail || "Error deleting client",
                "danger"
            );

        }

        Utils.loading(false);

    },

    refresh() {

        this.load();

    }

};