# Sistema Distribuido — Jinetes del Apocalipsis
**Universidad Austral de Chile · Sistemas Distribuidos**

---

## Arquitectura

```
                    ┌──────────────────────────────────┐
  Clientes          │          NGINX (puerto 80)        │  ← Balanceo de carga
  (demo_client)  →  │       Load Balancer               │     least_conn
                    └────────────┬─────────────┬────────┘
                                 │             │
                    ┌────────────▼──┐   ┌──────▼────────┐
                    │ API Gateway 1 │   │ API Gateway 2  │  ← Escalabilidad horizontal
                    │   (FastAPI)   │   │   (FastAPI)    │
                    └────────┬──────┘   └──────┬─────────┘
                             │                  │
               ┌─────────────┼──────────────────┘
               │             │
   ┌───────────▼──┐   ┌──────▼──────────┐   ┌────────────────┐
   │   PostgreSQL │   │ Service Manager │   │  Stats Service  │
   │   (datos)    │   │  (CRUD svcs)    │   │  (métricas)     │
   └──────────────┘   └─────────────────┘   └────────────────┘
```

## Funcionalidades implementadas

| # | Funcionalidad | Componente |
|---|--------------|-----------|
| ✅ | API Gateway centralizado | `api_gateway/` |
| ✅ | Gestión de servicios/endpoints | `service_manager/` |
| ✅ | Monitoreo y estadísticas | `stats_service/` + `/dashboard` |
| ✅ | Escalabilidad horizontal | 2 instancias gateway + NGINX |
| ✅ | Arquitectura de microservicios | 3 servicios desacoplados |
| ✅ | Comunicación distribuida cliente-servidor | `clients/` |
| ✅ | Persistencia en PostgreSQL | `scripts/init.sql` + SQLAlchemy |
| ✅ | Balanceo de carga | NGINX `least_conn` |
| ✅ | Tolerancia a fallos | Retry + Circuit Breaker en gateway |
| ✅ | SaaS / cloud computing | Docker Compose multi-contenedor |
| ✅ | Múltiples clientes concurrentes | `demo_client2` (asyncio) |
| ✅ | Recolección de métricas de uso | `usage_logs` + `metrics_hourly` |
| ✅ | Administración de servicios expuestos | CRUD en `service_manager` |
| ✅ | Procesamiento asíncrono | `asyncio`, background tasks, fire-and-forget |

## Estructura de carpetas

```
proyecto/
├── docker-compose.yml          # Orquestación de todos los servicios
├── start.sh                    # Script de arranque
├── scripts/
│   └── init.sql                # Esquema PostgreSQL + datos iniciales
├── shared/                     # Código compartido entre microservicios
│   ├── models.py               # Modelos SQLAlchemy
│   └── database.py             # Conexión async a PostgreSQL
├── api_gateway/                # Punto de entrada centralizado
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
├── service_manager/            # CRUD de servicios y clientes
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
├── stats_service/              # Monitoreo, métricas, dashboard
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
├── load_balancer/              # NGINX balanceador de carga
│   ├── nginx.conf
│   └── Dockerfile
└── clients/
    ├── requirements.txt
    ├── demo_client/
    │   └── client.py           # Demo: requests secuenciales y concurrentes
    └── demo_client2/
        └── client.py           # Demo: test de carga con workers paralelos
```

## Arranque rápido

```bash
# Levantar todo el sistema
bash start.sh

# O manualmente:
docker compose up --build -d

# Ejecutar clientes demo
pip install httpx
python clients/demo_client/client.py
python clients/demo_client2/client.py
```

## Endpoints principales

### API Gateway (via Load Balancer → puerto 80)
```
GET  /api/{service_name}       # Consumir servicio (requiere X-API-Key header)
GET  /health                   # Health check de la instancia
GET  /gateway/info             # Info de instancia + circuit breakers
```

### Service Manager (puerto 8001)
```
GET    /services               # Listar servicios
POST   /services               # Crear servicio
PUT    /services/{id}          # Actualizar servicio
DELETE /services/{id}          # Eliminar servicio
PATCH  /services/{id}/toggle   # Activar/desactivar en caliente
GET    /clients                # Listar clientes
POST   /clients                # Crear cliente
POST   /permissions            # Otorgar permiso
DELETE /permissions            # Revocar permiso
```

### Stats Service (puerto 8002 / dashboard en 8080)
```
GET /stats/overview            # Resumen global
GET /stats/services            # Métricas por servicio
GET /stats/clients             # Métricas por cliente
GET /stats/recent-logs         # Últimos N logs
GET /stats/gateways            # Distribución por instancia gateway
GET /dashboard                 # Dashboard HTML de monitoreo
```

## Clientes de prueba (preconfigurados en BD)

| Cliente | API Key | Servicios con acceso |
|---------|---------|---------------------|
| Cliente Demo | `testclient-key-001` | Todos (weather, quotes, ip_info, user_agent, echo) |
| Cliente Demo 2 | `testclient-key-002` | quotes, ip_info |

## Ejemplo de uso

```bash
# Consultar servicio de frases (con balanceo de carga)
curl -H "X-API-Key: testclient-key-001" http://localhost/api/quotes

# Ver qué instancia del gateway respondió
curl -v -H "X-API-Key: testclient-key-001" http://localhost/api/ip_info 2>&1 | grep X-Gateway

# Activar/desactivar un servicio en caliente
curl -X PATCH http://localhost:8001/services/1/toggle

# Ver estadísticas
curl http://localhost:8002/stats/overview
curl http://localhost:8002/stats/gateways   # distribución de carga
```

## Tolerancia a fallos

El gateway implementa:
- **Retry automático**: hasta 2 reintentos con backoff exponencial
- **Circuit Breaker**: si un servicio externo falla, se marca como "abierto" por 30s antes de reintentar
- **Timeout configurable** por servicio (campo `timeout_sec` en la BD)
- **Reinicio automático** de contenedores con `restart: on-failure`

## Tecnologías (Software Libre)

| Herramienta | Versión | Uso |
|-------------|---------|-----|
| Python | 3.12 | Lenguaje principal |
| FastAPI | 0.115 | Framework HTTP async |
| SQLAlchemy | 2.0 | ORM async para PostgreSQL |
| PostgreSQL | 16 | Base de datos relacional |
| NGINX | 1.25 | Balanceador de carga |
| Docker | — | Contenedores |
| httpx | 0.27 | Cliente HTTP async |
