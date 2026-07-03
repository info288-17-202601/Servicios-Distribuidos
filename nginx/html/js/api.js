const API = {

    base: "",

    manager: "/manager",

    gateway: "/api",

    stats: "/stats",

    token: null,

    setToken(token){

        this.token = token;

        localStorage.setItem("token",token);

    },

    loadToken(){

        this.token = localStorage.getItem("token");

    },

    headers(){

        const h = {
            "Content-Type":"application/json"
        };

        if(this.token){

            h["Authorization"]="Bearer "+this.token;

        }

        return h;

    },

    getAuthHeaders() {

        const token = Auth.token();

        return token
            ? { Authorization: `Bearer ${token}` }
            : {};

    },

    gatewayUrl(path) {

        return this.gateway + path;

    },

    managerUrl(path) {

        return this.manager + path;

    },

    statsUrl(path) {

        return this.stats + path;

    },

    statsGet(path) {

        return this.request(
            "GET",
            this.statsUrl(path)
        );

    },

    async get(url){

        const r = await fetch(url,{
            headers:this.headers()
        });

        return this.handle(r);

    },

    async post(url,data){

        const r = await fetch(url,{
            method:"POST",
            headers:this.headers(),
            body:JSON.stringify(data)
        });

        return this.handle(r);

    },

    async put(url,data){

        const r = await fetch(url,{
            method:"PUT",
            headers:this.headers(),
            body:JSON.stringify(data)
        });

        return this.handle(r);

    },

    async patch(url,data={}){

        const r = await fetch(url,{
            method:"PATCH",
            headers:this.headers(),
            body:JSON.stringify(data)
        });

        return this.handle(r);

    },

    async delete(url,data=null){

        const options={
            method:"DELETE",
            headers:this.headers()
        };

        if(data){

            options.body=JSON.stringify(data);

        }

        const r=await fetch(url,options);

        return this.handle(r);

    },

    async handle(response){

        if(response.status==204){

            return true;

        }

        let json={};

        try{

            json=await response.json();

        }catch(e){}

        if(!response.ok){

            throw json;

        }

        return json;

    },

    async request(method, url, body = null) {

        const headers = {

            "Content-Type": "application/json",

            ...this.getAuthHeaders()

        };

        const options = {

            method,

            headers

        };

        if (body) {

            options.body = JSON.stringify(body);

        }

        const response = await fetch(url, options);

        let data = null;

        try {

            data = await response.json();

        }
        catch (e) {

            data = null;

        }

        if (!response.ok) {

            throw {

                status: response.status,

                detail: data?.detail || "Request error"

            };

        }

        return data;

    }

};

API.loadToken();