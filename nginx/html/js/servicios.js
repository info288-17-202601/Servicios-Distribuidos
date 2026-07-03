const Services = {

    list: [],

    selectedId: null,

    async load() {

        Utils.loading(true);

        try {

            this.list = await API.get(
                API.managerUrl("/services")
            );

            this.renderTable();

        }
        catch (e) {

            Utils.toast(
                e.detail || "Could not load services",
                "danger"
            );

        }

        Utils.loading(false);

    },

    renderTable() {

        const tbody =
            document.getElementById("servicesTable");

        tbody.innerHTML = "";

        this.list.forEach(service => {

            tbody.innerHTML += `

            <tr>

                <td>${service.id}</td>

                <td>${service.name}</td>

                <td>
                    <span class="badge bg-secondary">
                        ${service.method}
                    </span>
                </td>

                <td>
                    <code>
                        ${service.endpoint}
                    </code>
                </td>

                <td>
                    ${
                        service.is_active
                        ? '<span class="badge bg-success">Active</span>'
                        : '<span class="badge bg-danger">Disabled</span>'
                    }
                </td>

                <td>

                    <button
                        class="btn btn-sm btn-primary"
                        onclick="Services.edit(${service.id})">

                        Edit

                    </button>

                    <button
                        class="btn btn-sm btn-warning"
                        onclick="Services.toggle(${service.id})">

                        Toggle

                    </button>

                    <button
                        class="btn btn-sm btn-danger"
                        onclick="Services.remove(${service.id})">

                        Delete

                    </button>

                </td>

            </tr>

            `;

        });

    },

    newService() {

        this.selectedId = null;

        this.showForm({

            name: "",

            description: "",

            endpoint: "",

            method: "GET",

            timeout_sec: 10

        });

    },

    async edit(id) {

        Utils.loading(true);

        try {

            const service =
                await API.get(
                    API.managerUrl("/services/" + id)
                );

            this.selectedId = id;

            this.showForm(service);

            bootstrap.Modal
                .getOrCreateInstance(
                    document.getElementById("serviceModal")
                )
                .show();

        }
        catch (e) {

            Utils.toast(
                e.detail || "Service not found",
                "danger"
            );

        }

        Utils.loading(false);

    },

        showForm(service) {

        const div =
            document.getElementById("serviceForm");

        div.innerHTML = `

        <div class="mb-3">

            <label class="form-label">

                Name

            </label>

            <input
                id="serviceName"
                class="form-control"
                value="${service.name}"
            >

        </div>

        <div class="mb-3">

            <label class="form-label">

                Description

            </label>

            <input
                id="serviceDesc"
                class="form-control"
                value="${service.description || ""}"
            >

        </div>

        <div class="mb-3">

            <label class="form-label">

                Endpoint

            </label>

            <input
                id="serviceEndpoint"
                class="form-control"
                value="${service.endpoint}"
            >

        </div>

        <div class="mb-3">

            <label class="form-label">

                Method

            </label>

            <select
                id="serviceMethod"
                class="form-select">

                <option value="GET" ${service.method === "GET" ? "selected" : ""}>GET</option>

                <option value="POST" ${service.method === "POST" ? "selected" : ""}>POST</option>

                <option value="PUT" ${service.method === "PUT" ? "selected" : ""}>PUT</option>

                <option value="DELETE" ${service.method === "DELETE" ? "selected" : ""}>DELETE</option>

            </select>

        </div>

        <div class="mb-3">

            <label class="form-label">

                Timeout (sec)

            </label>

            <input
                id="serviceTimeout"
                class="form-control"
                type="number"
                value="${service.timeout_sec || 10}"
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
                onclick="Services.save()">

                Save

            </button>

        </div>

        `;

    },

        async save() {

        const payload = {

            name: document.getElementById("serviceName").value.trim(),

            description: document.getElementById("serviceDesc").value.trim(),

            endpoint: document.getElementById("serviceEndpoint").value.trim(),

            method: document.getElementById("serviceMethod").value,

            timeout_sec: parseInt(
                document.getElementById("serviceTimeout").value
            )

        };

        if (!payload.name || !payload.endpoint) {

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
                    API.managerUrl("/services/" + this.selectedId),
                    payload
                );

                Utils.toast(
                    "Service updated",
                    "success"
                );

            }
            else {

                await API.post(
                    API.managerUrl("/services"),
                    payload
                );

                Utils.toast(
                    "Service created",
                    "success"
                );

            }

            bootstrap.Modal
                .getInstance(
                    document.getElementById("serviceModal")
                )
                .hide();

            await this.load();

            Dashboard.refresh();

        }
        catch (e) {

            Utils.toast(
                e.detail || "Error saving service",
                "danger"
            );

        }

        Utils.loading(false);

    },

    async toggle(id) {

        try {

            await API.patch(
                API.managerUrl("/services/" + id + "/toggle")
            );

            Utils.toast(
                "Service status updated",
                "success"
            );

            await this.load();

            Dashboard.refresh();

        }
        catch (e) {

            Utils.toast(
                e.detail || "Error toggling service",
                "danger"
            );

        }

    },

    async remove(id) {

        if (!confirm("Delete this service?")) {

            return;

        }

        Utils.loading(true);

        try {

            await API.delete(
                API.managerUrl("/services/" + id)
            );

            Utils.toast(
                "Service removed",
                "success"
            );

            await this.load();

            Dashboard.refresh();

        }
        catch (e) {

            Utils.toast(
                e.detail || "Error deleting service",
                "danger"
            );

        }

        Utils.loading(false);

    },

    refresh() {

        this.load();

    }

};