"""
API Gateway — Punto de entrada centralizado del sistema distribuido.
"""
import asyncio
import os
import time
import httpx
from contextlib import asynccontextmanager
from datetime import datetime
import redis.asyncio as redis

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import sys

sys.path.insert(0, "/app")
from shared.database import get_db, init_db, AsyncSessionLocal
from shared.models import Client, Service, ClientServicePermission, UsageLog

INSTANCE_ID       = os.getenv("INSTANCE_ID", "gateway_unknown")
STATS_SERVICE_URL = os.getenv("STATS_SERVICE_URL", "http://stats_service:8002")

MAX_RETRIES      = 2
CIRCUIT_OPEN: dict[str, int] = {}
CIRCUIT_COOLDOWN = 30

MAX_REQUESTS = 100 #Datos para rate limiting
WINDOW = 60


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="API Gateway",
    description="Punto de acceso centralizado al sistema distribuido",
    version="1.0.0",
    lifespan=lifespan,
)
#Conexión de redis para rate limiting
REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://redis:6379"
)
redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True
)


# Circuit breaker 
def is_circuit_open(service_name: str) -> bool:
    last_fail = CIRCUIT_OPEN.get(service_name, 0)
    return (time.time() - last_fail) < CIRCUIT_COOLDOWN

def mark_circuit_open(service_name: str):
    CIRCUIT_OPEN[service_name] = time.time()

def mark_circuit_closed(service_name: str):
    CIRCUIT_OPEN.pop(service_name, None)


#  Log asíncrono con su propia sesión de BD
async def log_usage_background(
    client_id: int | None,
    service_id: int | None,
    method: str,
    status_code: int,
    response_time_ms: int,
    client_ip: str,
):
    """Guarda el log de uso abriendo su propia sesión (no depende de la sesión del request)."""
    try:
        async with AsyncSessionLocal() as db:
            log = UsageLog(
                client_id=client_id,
                service_id=service_id,
                gateway_instance=INSTANCE_ID,
                request_method=method,
                status_code=status_code,
                response_time_ms=response_time_ms,
                client_ip=client_ip,
                requested_at=datetime.utcnow(),
            )
            db.add(log)
            await db.commit()
    except Exception as e:
        print(f"[log_usage] Error guardando log: {e}")

    # Notificar al stats service (best-effort)
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(f"{STATS_SERVICE_URL}/internal/ingest", json={
                "service_id":       service_id,
                "status_code":      status_code,
                "response_time_ms": response_time_ms,
            })
    except Exception:
        pass


#  Endpoints

@app.get("/health")
async def health():
    return {"status": "ok", "instance": INSTANCE_ID, "timestamp": datetime.utcnow().isoformat()}


@app.get("/gateway/info")
async def gateway_info():
    return {
        "instance_id":     INSTANCE_ID,
        "stats_service":   STATS_SERVICE_URL,
        "circuit_breakers": {k: "open" for k in CIRCUIT_OPEN},
    }


@app.api_route("/api/{service_name}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@app.api_route("/api/{service_name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_request(
    service_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    path: str = "",
):
    start_time = time.monotonic()
    client_ip  = request.client.host if request.client else "unknown"

    # Verificación de certificados con Nginx
    client_verified = request.headers.get("X-Client-Verify")
    client_dn       = request.headers.get("X-Client-DN")

    client_obj = None
    if api_key:
        result = await db.execute(
            select(Client).where(Client.api_key == api_key, Client.is_active == True)
        )
        client_obj = result.scalar_one_or_none()

    if client_obj and client_dn:
        if client_obj.cert_subject != client_dn:
            raise HTTPException(
                status_code=403,
                detail="El certificado presentado no coincide con el cliente autenticado por API Key"
            )

    api_key    = request.headers.get("X-API-Key", "").strip()

    # 1. Resolver cliente
    client_obj = None
    if api_key:
        result = await db.execute(select(Client).where(Client.api_key == api_key, Client.is_active == True))
        client_obj = result.scalar_one_or_none()

    # 2. Resolver servicio
    result = await db.execute(select(Service).where(Service.name == service_name, Service.is_active == True))
    service_obj = result.scalar_one_or_none()

    if not service_obj:

        elapsed = int((time.monotonic() - start_time) * 1000)

        asyncio.create_task(
            log_usage_background(
                client_obj.id if client_obj else None,
                None,
                request.method,
                404,
                elapsed,
                client_ip,
            )
        )

        raise HTTPException(status_code=404, detail=f"Servicio '{service_name}' no encontrado o inactivo")

    # 3. Verificar permiso
    if client_obj:
        perm = await db.execute(
            select(ClientServicePermission).where(
                ClientServicePermission.client_id  == client_obj.id,
                ClientServicePermission.service_id == service_obj.id,
            )
        )
        if not perm.scalar_one_or_none():
            elapsed = int((time.monotonic() - start_time) * 1000)
            asyncio.create_task(log_usage_background(
                client_obj.id, service_obj.id, request.method, 403, elapsed, client_ip
            ))
            raise HTTPException(status_code=403, detail="Sin permiso para usar este servicio")
        
        allowed = await check_rate_limit(client_obj.id)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit excedido"
            )

    # 4. Circuit breaker
    if is_circuit_open(service_name):

        elapsed = int((time.monotonic() - start_time) * 1000)

        asyncio.create_task(
            log_usage_background(
                client_obj.id if client_obj else None,
                service_obj.id,
                request.method,
                503,
                elapsed,
                client_ip,
            )
        )

        raise HTTPException(
            status_code=503,
            detail=f"Servicio '{service_name}' no disponible (circuit breaker)"
        )

    # 5. Construir URL destino
    target_url = service_obj.endpoint
    if "{city}" in target_url:
        city = request.query_params.get("city", "Santiago")
        target_url = target_url.replace("{city}", city)
    if path:
        target_url = target_url.rstrip("/") + "/" + path

    # 6. Reenviar solicitud con retry
    body    = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "x-api-key")}
    params  = {k: v for k, v in request.query_params.items() if k != "city"}

    last_exc = None
    last_status = 502

    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=service_obj.timeout_sec) as hclient:
                resp = await hclient.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    params=params,
                    content=body,
                )
            elapsed = int((time.monotonic() - start_time) * 1000)
            mark_circuit_closed(service_name)


            # Intentar devolver JSON, si no devolver texto plano envuelto
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body_data = resp.json()
                except Exception:
                    body_data = {"raw": resp.text}
            else:
                body_data = {"raw": resp.text}

            return JSONResponse(
                content=body_data,
                status_code=resp.status_code,
                headers={
                    "X-Gateway-Instance": INSTANCE_ID,
                    "X-Response-Time-Ms": str(elapsed),
                },
            )

        except httpx.ReadTimeout as exc:
            last_exc = exc
            last_status = 504

        except httpx.ConnectTimeout as exc:
            last_exc = exc
            last_status = 504

        except httpx.ConnectError as exc:
            last_exc = exc
            last_status = 502

        except Exception as exc:
            last_exc = exc
            last_status = 500

        await asyncio.sleep(0.5 * (attempt + 1))

    mark_circuit_open(service_name)
    elapsed = int((time.monotonic() - start_time) * 1000)

    asyncio.create_task(
        log_usage_background(
            client_obj.id if client_obj else None,
            service_obj.id,
            request.method,
            last_status,
            elapsed,
            client_ip,
        )
        )

    raise HTTPException(
        status_code=last_status,
        detail=str(last_exc)
        )
        status_code=502,
        detail=f"No se pudo conectar con '{service_name}' tras {MAX_RETRIES + 1} intentos"
    )

async def check_rate_limit(client_id: int):
    key = f"rate_limit:{client_id}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, WINDOW)

    return count <= MAX_REQUESTS

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=os.getenv("GATEWAY_HOST", "0.0.0.0"),
                port=int(os.getenv("GATEWAY_PORT", 8000)), reload=False)
