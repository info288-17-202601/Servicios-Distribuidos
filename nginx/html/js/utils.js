const Utils = {

    loading(state = true) {

        const el = document.getElementById("loading");

        if (!el) return;

        if (state) {

            el.classList.remove("d-none");

        }
        else {

            el.classList.add("d-none");

        }

    },

    toast(message, type = "info") {

        const toastEl = document.getElementById("mainToast");

        const body = document.getElementById("toastBody");

        if (!toastEl || !body) return;

        body.innerHTML = message;

        toastEl.className = `toast text-bg-${type}`;

        const t = bootstrap.Toast.getOrCreateInstance(toastEl);

        t.show();

    },

    value(id) {

        const el = document.getElementById(id);

        return el ? el.value.trim() : "";

    },

    setText(id, value) {

        const el = document.getElementById(id);

        if (el) {

            el.innerText = value;

        }

    },

    formatDate(dateStr) {

        try {

            const d = new Date(dateStr);

            return d.toLocaleString();

        }
        catch (e) {

            return dateStr;

        }

    },

    safeJson(value) {

        try {

            return JSON.parse(value);

        }
        catch (e) {

            return null;

        }

    },

    clearForm(ids = []) {

        ids.forEach(id => {

            const el = document.getElementById(id);

            if (el) {

                el.value = "";

            }

        });

    },

};