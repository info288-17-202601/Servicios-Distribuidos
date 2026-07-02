"""
Cliente Demo 1 — Aplicación cliente que consume servicios via el API Gateway.
"""
import asyncio
import httpx
import json
from datetime import datetime

GATEWAY_URL = "http://localhost:80"
API_KEY     = "testclient-key-001"

HEADERS = {
    "X-API-Key":    API_KEY,
    "Content-Type": "application/json",
}


def print_banner():
    print("\n" + "="*60)
    print("  CLIENTE DEMO 1 — Sistema Distribuido")
    print(f"  Gateway: {GATEWAY_URL}")
    print(f"  API Key: {API_KEY}")
    print("="*60 + "\n")


def safe_json(resp: httpx.Response) -> dict | None:
    """Parsea JSON sin crashear si la respuesta está vacía o no es JSON."""
    try:
        return resp.json()
    except Exception:
        return None


async def call_service(client: httpx.AsyncClient, service_name: str, params: dict = None, body: dict = None):
    try:
        url = f"{GATEWAY_URL}/api/{service_name}"
        if body:
            resp = await client.post(url, headers=HEADERS, params=params, json=body)
        else:
            resp = await client.get(url, headers=HEADERS, params=params)

        gateway_instance = resp.headers.get("X-Gateway-Instance", "?")
        response_time    = resp.headers.get("X-Response-Time-Ms", "?")

        print(f"[{service_name}]")
        print(f"  Instancia Gateway : {gateway_instance}")
        print(f"  HTTP Status       : {resp.status_code}")
        print(f"  Tiempo respuesta  : {response_time}ms")

        data = safe_json(resp)
        if resp.status_code == 200 and data:
            preview = json.dumps(data, ensure_ascii=False)[:200]
            print(f"  Respuesta         : {preview}...")
        elif data and "detail" in data:
            print(f"  Error             : {data['detail']}")
        else:
            print(f"  Respuesta         : {resp.text[:200]}")

    except httpx.ConnectError:
        print(f"[{service_name}] ERROR: No se pudo conectar al gateway ({GATEWAY_URL})")
    except Exception as e:
        print(f"[{service_name}] ERROR inesperado: {e}")
    print()


async def demo_concurrent_requests():
    print("── Requests Concurrentes (asyncio.gather) ──────────────")
    async with httpx.AsyncClient(timeout=15.0) as client:
        await asyncio.gather(
            call_service(client, "quotes"),
            call_service(client, "ip_info"),
            call_service(client, "user_agent"),
            call_service(client, "quotes"),
            call_service(client, "ip_info"),
        )


async def demo_sequential_requests():
    print("── Requests Secuenciales ────────────────────────────────")
    async with httpx.AsyncClient(timeout=15.0) as client:
        await call_service(client, "quotes")
        await call_service(client, "ip_info")
        await call_service(client, "echo", body={
            "mensaje":   "hola desde cliente demo",
            "timestamp": datetime.utcnow().isoformat(),
        })


async def demo_forbidden_service():
    print("── Verificación de Permisos ─────────────────────────────")
    async with httpx.AsyncClient(timeout=10.0) as client:
        print("Cliente 1 → weather (tiene permiso):")
        resp = await client.get(
            f"{GATEWAY_URL}/api/weather",
            headers={"X-API-Key": "testclient-key-001"},
            params={"city": "Valdivia"},
        )
        data = safe_json(resp)
        detail = data.get("detail", "") if data else resp.text[:100]
        print(f"  Status: {resp.status_code} | Gateway: {resp.headers.get('X-Gateway-Instance','?')}")
        if detail:
            print(f"  Detalle: {detail}")
        print()

        print("Cliente 2 → weather (sin permiso):")
        resp2 = await client.get(
            f"{GATEWAY_URL}/api/weather",
            headers={"X-API-Key": "testclient-key-002"},
            params={"city": "Valdivia"},
        )
        data2 = safe_json(resp2)
        detail2 = data2.get("detail", "") if data2 else resp2.text[:100]
        print(f"  Status: {resp2.status_code} | Mensaje: {detail2}")
        print()


async def demo_load_balancing():
    print("── Distribución de Carga (10 requests) ─────────────────")
    instances: dict[str, int] = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks     = [client.get(f"{GATEWAY_URL}/health") for _ in range(10)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for resp in responses:
            if isinstance(resp, Exception):
                continue
            data = safe_json(resp)
            inst = data.get("instance", "?") if data else "?"
            instances[inst] = instances.get(inst, 0) + 1

    for inst, count in instances.items():
        bar = "█" * count
        print(f"  {inst:20s} {bar} ({count})")
    print()


async def main():
    print_banner()
    await demo_concurrent_requests()
    await demo_sequential_requests()
    await demo_forbidden_service()
    await demo_load_balancing()

    print("── Estadísticas del Sistema ─────────────────────────────")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get("http://localhost:8002/stats/overview")
        if resp.status_code == 200:
            ov = safe_json(resp) or {}
            print(f"  Total requests    : {ov.get('total_requests', '?')}")
            print(f"  Requests 24h      : {ov.get('requests_last_24h', '?')}")
            print(f"  Servicios activos : {ov.get('active_services', '?')}")
            print(f"  Clientes activos  : {ov.get('active_clients', '?')}")
            print(f"  Avg response      : {ov.get('avg_response_time_ms', '?')}ms")
    print()
    print("✓ Demo completado. Abre http://localhost:8080/dashboard para ver el monitor.")


if __name__ == "__main__":
    asyncio.run(main())
