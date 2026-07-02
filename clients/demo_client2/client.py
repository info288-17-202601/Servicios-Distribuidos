"""
Cliente Demo 2 — Generador de carga concurrente.

Demuestra:
  • Múltiples clientes simultáneos
  • Escalabilidad horizontal bajo carga
  • Procesamiento asíncrono masivo
  • Métricas de rendimiento en tiempo real
"""
import asyncio
import httpx
import time
import random
from datetime import datetime

GATEWAY_URL  = "http://localhost:80"
API_KEY      = "testclient-key-002"   # Cliente con acceso limitado (quotes, ip_info)
ADMIN_STATS  = "http://localhost:8002"

SERVICES_AVAILABLE = ["quotes", "ip_info"]  # solo los que tiene permiso


async def single_request(client: httpx.AsyncClient, worker_id: int, service: str) -> dict:
    start = time.monotonic()
    try:
        resp = await client.get(
            f"{GATEWAY_URL}/api/{service}",
            headers={"X-API-Key": API_KEY},
        )
        elapsed = int((time.monotonic() - start) * 1000)
        instance = resp.headers.get("X-Gateway-Instance", "?")
        return {"worker": worker_id, "service": service, "status": resp.status_code,
                "ms": elapsed, "instance": instance, "ok": resp.status_code < 400}
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return {"worker": worker_id, "service": service, "status": 0,
                "ms": elapsed, "instance": "?", "ok": False, "error": str(e)}


async def worker(worker_id: int, n_requests: int, results: list):
    async with httpx.AsyncClient(timeout=15.0) as client:
        for i in range(n_requests):
            service = random.choice(SERVICES_AVAILABLE)
            result  = await single_request(client, worker_id, service)
            results.append(result)
            await asyncio.sleep(random.uniform(0.05, 0.3))


async def run_load_test(n_workers: int = 5, requests_per_worker: int = 4):
    print(f"\n{'='*60}")
    print(f"  CLIENTE DEMO 2 — Test de Carga Concurrente")
    print(f"  Workers: {n_workers} | Requests/worker: {requests_per_worker}")
    print(f"  Total requests: {n_workers * requests_per_worker}")
    print(f"{'='*60}\n")

    results = []
    start   = time.monotonic()

    # Lanzar todos los workers en paralelo (simula clientes concurrentes)
    await asyncio.gather(*[
        worker(i + 1, requests_per_worker, results)
        for i in range(n_workers)
    ])

    elapsed_total = time.monotonic() - start

    # Análisis de resultados
    total    = len(results)
    ok       = sum(1 for r in results if r["ok"])
    errors   = total - ok
    avg_ms   = sum(r["ms"] for r in results) / total if total else 0
    max_ms   = max(r["ms"] for r in results) if results else 0
    min_ms   = min(r["ms"] for r in results) if results else 0

    # Distribución por instancia de gateway
    by_instance: dict[str, int] = {}
    for r in results:
        inst = r["instance"]
        by_instance[inst] = by_instance.get(inst, 0) + 1

    # Distribución por servicio
    by_service: dict[str, int] = {}
    for r in results:
        svc = r["service"]
        by_service[svc] = by_service.get(svc, 0) + 1

    print("── Resultados ───────────────────────────────────────────")
    print(f"  Total requests    : {total}")
    print(f"  Exitosos (2xx)    : {ok}")
    print(f"  Errores           : {errors}")
    print(f"  Tasa de éxito     : {ok/total*100:.1f}%")
    print(f"  Tiempo total      : {elapsed_total:.2f}s")
    print(f"  Throughput        : {total/elapsed_total:.1f} req/s")
    print(f"  Resp. promedio    : {avg_ms:.0f}ms")
    print(f"  Resp. mínima      : {min_ms}ms")
    print(f"  Resp. máxima      : {max_ms}ms")

    print("\n── Distribución por Gateway (Balanceo de Carga) ─────────")
    for inst, count in sorted(by_instance.items()):
        pct = count / total * 100
        bar = "█" * int(pct / 5)
        print(f"  {inst:20s} {bar:20s} {count:3d} ({pct:.1f}%)")

    print("\n── Distribución por Servicio ─────────────────────────────")
    for svc, count in sorted(by_service.items()):
        print(f"  {svc:20s} {count:3d} requests")

    print("\n── Stats del Sistema (en tiempo real) ───────────────────")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{ADMIN_STATS}/stats/overview")
            if r.status_code == 200:
                ov = r.json()
                print(f"  Total global      : {ov['total_requests']}")
                print(f"  Error rate        : {ov['total_errors']/max(ov['total_requests'],1)*100:.1f}%")
                print(f"  Avg respuesta     : {ov['avg_response_time_ms']}ms")

            r2 = await client.get(f"{ADMIN_STATS}/stats/gateways")
            if r2.status_code == 200:
                gws = r2.json()
                print("\n  Instancias activas en gateway cluster:")
                for gw in gws:
                    print(f"    {gw['instance']}: {gw['requests']} requests acumulados")
    except Exception as e:
        print(f"  (No se pudo conectar al stats service: {e})")

    print(f"\n✓ Test finalizado. Dashboard: http://localhost:8080/dashboard\n")


if __name__ == "__main__":
    asyncio.run(run_load_test(n_workers=5, requests_per_worker=4))
