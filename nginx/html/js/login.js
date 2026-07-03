window.onload = () => {

    comprobarServidor();

    document
        .getElementById("btnLogin")
        .addEventListener("click", login);

};

async function comprobarServidor() {

    try {

        await API.get("/manager/health");

        const estado = document.getElementById("serverStatus");

        estado.innerHTML = "Servidor conectado";

        estado.className = "text-success text-center";

    }
    catch {

        const estado = document.getElementById("serverStatus");

        estado.innerHTML = "Servidor no disponible";

        estado.className = "text-danger text-center";

    }

}

async function login() {

    const usuario = document
        .getElementById("txtUser")
        .value
        .trim();

    const password = document
        .getElementById("txtPassword")
        .value
        .trim();

    const rol = document
        .getElementById("cmbRole")
        .value;

    if (usuario === "" || password === "") {

        Utils.toast(
            "Debe completar todos los campos",
            "danger"
        );

        return;

    }

    Utils.loading(true);

    try {

        let respuesta;

        if (rol === "admin") {

            respuesta = await API.post(
                "/manager/login",
                {
                    username: usuario,
                    password: password
                }
            );

            Auth.login(
                respuesta.token,
                {
                    username: usuario,
                    role: "admin"
                }
            );

            location = "admin.html";

        }
        else {

            respuesta = await API.post(
                "/manager/client/login",
                {
                    email: usuario,
                    api_key: password
                }
            );

            Auth.login(
                respuesta.token,
                {
                    email: usuario,
                    role: "client"
                }
            );

            location = "cliente.html";

        }

    }
    catch (e) {

        Utils.toast(
            e.detail || "No fue posible iniciar sesión",
            "danger"
        );

    }

    Utils.loading(false);

}