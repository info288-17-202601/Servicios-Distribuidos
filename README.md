# Sistema Distribuido — Especificación de Despliegue

## Requisitos

- Docker >= 24
- Docker Compose >= 2.20
- Python >= 3.10 (solo para ejecutar los clientes demo)
- python-jose y passlib (para el panel)

```bash
#esto instala lo necesario para el panel
pip install python-jose[cryptography] passlib[bcrypt]
```

---

## Estructura del proyecto

```
proyecto/
├── .env                        # Variables de entorno (único archivo a editar para configurar)
├── docker-compose.yml          # Orquestación de contenedores
├── scripts/init.sql            # Esquema de base de datos y datos iniciales
├── shared/                     # Modelos y conexión a BD compartidos entre servicios
├── api_gateway/                # Punto de entrada centralizado (corre en 2 instancias)
├── service_manager/            # CRUD de servicios, clientes y permisos
├── stats_service/              # Métricas, logs de uso y dashboard de monitoreo
├── load_balancer/              # NGINX como balanceador de carga
└── clients/                    # Clientes demo para probar el sistema
```

---

## Despliegue en una sola máquina

El archivo `.env` ya viene configurado para uso local. No requiere ningún cambio.

```bash
# Levantar todos los servicios
docker compose up --build -d

# Verificar que todos los contenedores estén corriendo
docker compose ps

# Ver logs de un servicio específico
docker compose logs -f api_gateway_1
```

Una vez levantado, los endpoints disponibles son:

| Servicio | URL |
|---|---|
| Service Manager (docs) | http://localhost:8001/docs |
| Stats Service (docs) | http://localhost:8002/docs |
| Dashboard de monitoreo | http://localhost:8080/dashboard |

---

## Despliegue en múltiples máquinas

En un despliegue distribuido cada VM corre solo los contenedores que le corresponden, con su propio `docker-compose.yml` recortado. Lo único que cambia respecto al despliegue local son los valores del `.env` en cada máquina.

**Pasos:**

1. Copiar el proyecto completo en cada VM.
2. Editar el `.env` en cada VM reemplazando los hosts internos de Docker por las IPs reales de las otras máquinas (ver tabla de variables más abajo).
3. Editar `load_balancer/nginx.conf` reemplazando los nombres de contenedor por las IPs reales de las VMs que corren los gateways:

```nginx
# Cambiar esto:
server api_gateway_1:8000;
server api_gateway_2:8000;

# Por las IPs reales, por ejemplo:
server 192.168.1.20:8000;
server 192.168.1.30:8000;
```

Y también esta línea del mismo archivo:

```nginx
# Cambiar esto:
proxy_pass http://stats_service:8002;

# Por la IP real del stats service:
proxy_pass http://192.168.1.40:8002;
```

4. En cada VM, levantar solo los servicios correspondientes:

```bash
# VM con la base de datos
docker compose up --build -d postgres

# VM con el service manager
docker compose up --build -d service_manager

# VM con el stats service
docker compose up --build -d stats_service

# VM con gateway 1
docker compose up --build -d api_gateway_1

# VM con gateway 2
docker compose up --build -d api_gateway_2

# VM con el balanceador
docker compose up --build -d nginx
```

---

## Variables de entorno

Todas las variables se configuran en el archivo `.env` en la raíz del proyecto. Docker Compose lo lee automáticamente.

### Base de datos PostgreSQL

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `POSTGRES_HOST` | `postgres` | Host donde corre PostgreSQL. En multi-máquina: IP de esa VM. |
| `POSTGRES_PORT` | `5432` | Puerto de PostgreSQL. |
| `POSTGRES_USER` | `admin` | Usuario de la base de datos. |
| `POSTGRES_PASSWORD` | `admin123` | Contraseña de la base de datos. |
| `POSTGRES_DB` | `distributed_sys` | Nombre de la base de datos. |
| `DATABASE_URL` | *(construida automáticamente)* | URL de conexión async completa usada por todos los servicios Python. Se construye a partir de las variables anteriores. En multi-máquina se puede escribir directamente con la IP real. |

### Service Manager

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `SERVICE_MANAGER_HOST` | `service_manager` | Host del service manager. En multi-máquina: IP de esa VM. |
| `SERVICE_MANAGER_PORT` | `8001` | Puerto donde escucha el service manager. |
| `SERVICE_MANAGER_URL` | *(construida automáticamente)* | URL completa usada por otros servicios para comunicarse con el service manager. |

### Stats Service

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `STATS_SERVICE_HOST` | `stats_service` | Host del stats service. En multi-máquina: IP de esa VM. |
| `STATS_SERVICE_PORT` | `8002` | Puerto donde escucha el stats service. |
| `STATS_SERVICE_URL` | *(construida automáticamente)* | URL completa usada por el gateway para notificar eventos de uso al stats service. |

### API Gateway

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `GATEWAY_PORT` | `8000` | Puerto donde escucha cada instancia del gateway. |
| `GATEWAY_1_INSTANCE_ID` | `gateway_1` | Identificador único de la primera instancia. Aparece en los headers de respuesta y en las métricas para identificar qué instancia atendió cada request. |
| `GATEWAY_2_INSTANCE_ID` | `gateway_2` | Identificador único de la segunda instancia. Si se despliega en una VM separada, cambiar este valor en el `.env` de esa VM. |

### NGINX (Load Balancer)

NGINX no lee variables de entorno directamente. Sus valores se configuran editando `load_balancer/nginx.conf` a mano. Las siguientes variables están en el `.env` solo como referencia documentada de qué habría que cambiar en ese archivo:

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `NGINX_GATEWAY_1` | `api_gateway_1:8000` | Referencia al servidor de la primera instancia del gateway en el upstream de NGINX. |
| `NGINX_GATEWAY_2` | `api_gateway_2:8000` | Referencia al servidor de la segunda instancia del gateway en el upstream de NGINX. |

---

## Clientes demo

Requieren tener `httpx` instalado:

```bash
pip install httpx
```

**Cliente 1** — Realiza requests secuenciales y concurrentes a distintos servicios, verifica permisos y muestra la distribución de carga entre instancias del gateway:

```bash
python clients/demo_client/client.py
```

**Cliente 2** — Genera carga concurrente con múltiples workers en paralelo y muestra estadísticas de rendimiento:

```bash
python clients/demo_client2/client.py
```

Los clientes se conectan al gateway vía `http://localhost:80` usando las siguientes API keys precargadas en la base de datos:

| Cliente | API Key | Servicios con acceso |
|---|---|---|
| Cliente Demo 1 | `testclient-key-001` | Todos (weather, quotes, ip_info, user_agent, echo) |
| Cliente Demo 2 | `testclient-key-002` | quotes, ip_info |

---

## Servicios precargados

La base de datos se inicializa automáticamente con cinco servicios de ejemplo registrados en la tabla `services`. Cada uno tiene una URL externa real asociada que el gateway contacta al recibir un request:

| Nombre | Método | Descripción |
|---|---|---|
| `quotes` | GET | Frase aleatoria motivacional |
| `ip_info` | GET | Información de la IP pública del request |
| `user_agent` | GET | User-agent del cliente |
| `weather` | GET | Clima por ciudad (parámetro: `?city=Valdivia`) |
| `echo` | POST | Devuelve el cuerpo del request |

Nuevos servicios se agregan vía el Service Manager en `http://localhost:8001/docs`.

---

## Detener el sistema

```bash
# Detener y eliminar contenedores (los datos en PostgreSQL se conservan)
docker compose down

# Detener y eliminar también el volumen de datos
docker compose down -v
```
