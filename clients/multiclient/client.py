"""
multi_client_demo.py — Simulación de múltiples clientes reales usando el sistema.

Clientes:
  1. MeteoSur         → usa 'weather'       (pronósticos climáticos para el sur de Chile)
  2. MenteClara       → usa 'quotes'        (app de psicología y bienestar)
  3. NetScan          → usa 'ip_info'       (herramienta de diagnóstico de red)
  4. AgentDetect      → usa 'user_agent'    (analítica de dispositivos)
  5. EchoTest         → usa 'echo'          (servicio de QA / testing interno)

Casos especiales demostrados:
  - MeteoSur intenta usar 'quotes' → no tiene permiso (403)
  - EchoTest provoca un timeout usando un servicio con timeout_sec=1 apuntando a una URL lenta
"""

import asyncio
import httpx
import json
import secrets
from datetime import datetime

GATEWAY_URL      = "http://localhost:80"
SERVICE_MANAGER  = "http://localhost:8001"
STATS_URL        = "http://localhost:8002"

# ─── Definición de clientes temáticos ───────────────────────
CLIENTES = [
    {
        "name":       "MeteoSur",
        "email":      "contacto@meteosur.cl",
        "api_key":    f"meteosur-{secrets.token_hex(6)}",
        "services":   ["weather"],
        "descripcion": "Plataforma de pronósticos climáticos para el sur de Chile",
    },
    {
        "name":       "MenteClara",
        "email":      "api@menteclara.org",
        "api_key":    f"menteclara-{secrets.token_hex(6)}",
        "services":   ["quotes"],
        "descripcion": "App de psicología positiva y bienestar emocional",
    },
    {
        "name":       "NetScan",
        "email":      "sistemas@netscan.io",
        "api_key":    f"netscan-{secrets.token_hex(6)}",
        "services":   ["ip_info", "user_agent"],
        "descripcion": "Herramienta de diagnóstico y análisis de red",
    },
    {
        "name":       "AgentDetect",
        "email":      "dev@agentdetect.com",
        "api_key":    f"agentdetect-{secrets.token_hex(6)}",
        "services":   ["user_agent", "ip_info"],
        "descripcion": "Plataforma de analítica de dispositivos y navegadores",
    },
    {
        "name":       "EchoTest",
        "email":      "qa@echotest.dev",
        "api_key":    f"echotest-{secrets.token_hex(6)}",
        "services":   ["echo"],
        "descripcion": "Servicio interno de QA y pruebas de integración",
    },
]

# Referencia global: nombre → api_key (se llena al registrar)
KEYS: dict[str, str] = {}


# ─── Helpers ────────────────────────────────────────────────

def safe_json(resp: httpx.Response):
    try:
        return resp.json()
    except Exception:
        return None


def encabezado(titulo: str):
    print(f"\n{'─'*60}")
    print(f"  {titulo}")
    print(f"{'─'*60}")


def resultado(ok: bool, servicio: str, status: int, gateway: str, ms: str, detalle: str = ""):
    icono = "✓" if ok else "✗"
    print(f"  {icono} [{servicio}] status={status} gateway={gateway} ({ms}ms)")
    if detalle:
        print(f"    → {detalle}")


# ─── Registro de clientes en el sistema ─────────────────────

async def registrar_clientes():
    """Crea los clientes y sus permisos vía el Service Manager."""
    encabezado("Registrando clientes en el sistema")

    # Obtener mapa de nombres de servicios → IDs
    async with httpx.AsyncClient(timeout=10.0) as http:
        r = await http.get(f"{SERVICE_MANAGER}/services")
        if r.status_code != 200:
            print("  ERROR: No se pudo conectar al Service Manager.")
            print("  ¿Está el sistema corriendo? (docker compose up -d)")
            raise SystemExit(1)

        servicios = {s["name"]: s["id"] for s in r.json()}

        for c in CLIENTES:
            # Crear cliente (ignorar si ya existe)
            payload = {"name": c["name"], "email": c["email"], "api_key": c["api_key"]}
            r = await http.post(f"{SERVICE_MANAGER}/clients", json=payload)

            if r.status_code == 201:
                client_id = r.json()["id"]
                KEYS[c["name"]] = c["api_key"]
                print(f"  + {c['name']:15s} registrado (id={client_id})")
            elif r.status_code == 409:
                # Ya existe, obtener su id buscando por email
                todos = await http.get(f"{SERVICE_MANAGER}/clients")
                existente = next((x for x in todos.json() if x["email"] == c["email"]), None)
                if existente:
                    client_id = existente["id"]
                    KEYS[c["name"]] = existente["api_key"]
                    c["api_key"] = existente["api_key"]
                    print(f"  ~ {c['name']:15s} ya existe (id={client_id}), usando api_key existente")
                else:
                    print(f"  ! {c['name']:15s} conflicto al registrar, saltando")
                    continue
            else:
                print(f"  ! {c['name']:15s} error {r.status_code}: {r.text}")
                continue

            # Otorgar permisos a los servicios que le corresponden
            for svc_name in c["services"]:
                svc_id = servicios.get(svc_name)
                if not svc_id:
                    print(f"    ! Servicio '{svc_name}' no encontrado en el sistema")
                    continue
                pr = await http.post(f"{SERVICE_MANAGER}/permissions",
                                     json={"client_id": client_id, "service_id": svc_id})
                if pr.status_code in (201, 409):
                    print(f"    ✓ permiso → {svc_name}")
                else:
                    print(f"    ! permiso → {svc_name} falló ({pr.status_code})")


# ─── Registrar servicio lento para prueba de timeout ────────

async def registrar_servicio_lento():
    """Agrega un servicio con timeout_sec=1 apuntando a una URL que tarda."""
    async with httpx.AsyncClient(timeout=10.0) as http:
        payload = {
            "name":        "lento",
            "description": "Servicio de prueba que provoca timeout (delay de 5s)",
            "endpoint":    "https://httpbin.org/delay/5",
            "method":      "GET",
            "timeout_sec": 1,   # el gateway espera solo 1 segundo → timeout garantizado
            "is_active":   True,
        }
        r = await http.post(f"{SERVICE_MANAGER}/services", json=payload)
        if r.status_code == 201:
            svc_id = r.json()["id"]
            print(f"\n  + Servicio 'lento' registrado (id={svc_id}, timeout=1s)")

            # Dar permiso a EchoTest para usarlo
            todos = await http.get(f"{SERVICE_MANAGER}/clients")
            echotest = next((x for x in todos.json() if x["name"] == "EchoTest"), None)
            if echotest:
                await http.post(f"{SERVICE_MANAGER}/permissions",
                                json={"client_id": echotest["id"], "service_id": svc_id})
                print(f"    ✓ permiso → EchoTest puede usar 'lento'")
        elif r.status_code == 409:
            print(f"\n  ~ Servicio 'lento' ya existe")
        else:
            print(f"\n  ! No se pudo registrar servicio lento: {r.text}")


# ─── Requests de cada cliente ────────────────────────────────

async def meteosur(client: httpx.AsyncClient):
    encabezado("MeteoSur — Pronósticos climáticos")
    print(f"  {CLIENTES[0]['descripcion']}\n")

    for ciudad in ["Valdivia", "Puerto Montt", "Punta Arenas"]:
        r = await client.get(f"{GATEWAY_URL}/api/weather",
                             headers={"X-API-Key": KEYS["MeteoSur"]},
                             params={"city": ciudad})
        gw = r.headers.get("X-Gateway-Instance", "?")
        ms = r.headers.get("X-Response-Time-Ms", "?")
        data = safe_json(r)
        detalle = f"clima de {ciudad} obtenido" if r.status_code == 200 else (data or {}).get("detail", r.text[:60])
        resultado(r.status_code == 200, "weather", r.status_code, gw, ms, detalle)
        await asyncio.sleep(0.3)


async def menteclara(client: httpx.AsyncClient):
    encabezado("MenteClara — Bienestar y psicología")
    print(f"  {CLIENTES[1]['descripcion']}\n")

    for sesion in range(1, 5):
        r = await client.get(f"{GATEWAY_URL}/api/quotes",
                             headers={"X-API-Key": KEYS["MenteClara"]})
        gw = r.headers.get("X-Gateway-Instance", "?")
        ms = r.headers.get("X-Response-Time-Ms", "?")
        data = safe_json(r)
        if r.status_code == 200 and data:
            frase = data.get("quote", data.get("raw", ""))
            detalle = f'"{str(frase)[:70]}..."' if len(str(frase)) > 70 else f'"{frase}"'
        else:
            detalle = (data or {}).get("detail", r.text[:60])
        resultado(r.status_code == 200, "quotes", r.status_code, gw, ms, detalle)
        await asyncio.sleep(0.2)


async def netscan(client: httpx.AsyncClient):
    encabezado("NetScan — Diagnóstico de red")
    print(f"  {CLIENTES[2]['descripcion']}\n")

    for _ in range(3):
        r = await client.get(f"{GATEWAY_URL}/api/ip_info",
                             headers={"X-API-Key": KEYS["NetScan"]})
        gw  = r.headers.get("X-Gateway-Instance", "?")
        ms  = r.headers.get("X-Response-Time-Ms", "?")
        data = safe_json(r)
        ip  = (data or {}).get("origin", "?") if r.status_code == 200 else (data or {}).get("detail", "")
        resultado(r.status_code == 200, "ip_info", r.status_code, gw, ms, f"IP origen: {ip}")
        await asyncio.sleep(0.2)

    r = await client.get(f"{GATEWAY_URL}/api/user_agent",
                         headers={"X-API-Key": KEYS["NetScan"]})
    gw  = r.headers.get("X-Gateway-Instance", "?")
    ms  = r.headers.get("X-Response-Time-Ms", "?")
    data = safe_json(r)
    ua  = (data or {}).get("user-agent", "?") if r.status_code == 200 else ""
    resultado(r.status_code == 200, "user_agent", r.status_code, gw, ms, f"UA: {str(ua)[:60]}")


async def agentdetect(client: httpx.AsyncClient):
    encabezado("AgentDetect — Analítica de dispositivos")
    print(f"  {CLIENTES[3]['descripcion']}\n")

    agentes = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
        "python-httpx/0.27.2",
    ]
    for ua in agentes:
        r = await client.get(f"{GATEWAY_URL}/api/user_agent",
                             headers={"X-API-Key": KEYS["AgentDetect"], "User-Agent": ua})
        gw  = r.headers.get("X-Gateway-Instance", "?")
        ms  = r.headers.get("X-Response-Time-Ms", "?")
        resultado(r.status_code == 200, "user_agent", r.status_code, gw, ms,
                  f"UA enviado: {ua[:55]}")
        await asyncio.sleep(0.2)


async def echotest(client: httpx.AsyncClient):
    encabezado("EchoTest — QA y pruebas de integración")
    print(f"  {CLIENTES[4]['descripcion']}\n")

    payloads = [
        {"test": "ping",      "timestamp": datetime.utcnow().isoformat(), "version": "1.0"},
        {"test": "payload",   "data": list(range(10)), "nested": {"ok": True}},
        {"test": "unicode",   "mensaje": "Conexión establecida correctamente ✓"},
    ]
    for p in payloads:
        r = await client.post(f"{GATEWAY_URL}/api/echo",
                              headers={"X-API-Key": KEYS["EchoTest"]},
                              json=p)
        gw  = r.headers.get("X-Gateway-Instance", "?")
        ms  = r.headers.get("X-Response-Time-Ms", "?")
        resultado(r.status_code == 200, "echo", r.status_code, gw, ms,
                  f"payload '{p['test']}' enviado y recibido")
        await asyncio.sleep(0.2)


# ─── Caso especial: acceso sin permiso ──────────────────────

async def caso_sin_permiso(client: httpx.AsyncClient):
    encabezado("CASO ESPECIAL — Acceso denegado (403)")
    print("  MeteoSur intenta usar 'quotes' sin tener permiso\n")

    r = await client.get(f"{GATEWAY_URL}/api/quotes",
                         headers={"X-API-Key": KEYS["MeteoSur"]})
    gw   = r.headers.get("X-Gateway-Instance", "?")
    ms   = r.headers.get("X-Response-Time-Ms", "?")
    data = safe_json(r)
    msg  = (data or {}).get("detail", r.text[:80])
    resultado(False, "quotes", r.status_code, gw, ms, f"Respuesta del gateway: {msg}")


# ─── Caso especial: timeout ──────────────────────────────────

async def caso_timeout(client: httpx.AsyncClient):
    encabezado("CASO ESPECIAL — Timeout y Circuit Breaker (502/503)")
    print("  EchoTest llama al servicio 'lento' (timeout configurado en 1s, demora real 5s)")
    print("  El gateway reintentará 2 veces antes de abrir el circuit breaker\n")

    # Primer intento → debería dar 502 tras agotar retries
    print("  Intento 1 (esperar agotamiento de retries)...")
    r = await client.get(f"{GATEWAY_URL}/api/lento",
                         headers={"X-API-Key": KEYS["EchoTest"]},
                         timeout=30.0)
    gw   = r.headers.get("X-Gateway-Instance", "?")
    ms   = r.headers.get("X-Response-Time-Ms", "?")
    data = safe_json(r)
    msg  = (data or {}).get("detail", r.text[:80])
    resultado(False, "lento", r.status_code, gw, ms, msg)

    # Segundo intento inmediato → debería dar 503 (circuit breaker abierto)
    print("\n  Intento 2 inmediato (circuit breaker debería estar abierto)...")
    r2   = await client.get(f"{GATEWAY_URL}/api/lento",
                            headers={"X-API-Key": KEYS["EchoTest"]},
                            timeout=10.0)
    gw2  = r2.headers.get("X-Gateway-Instance", "?")
    ms2  = r2.headers.get("X-Response-Time-Ms", "?")
    data2 = safe_json(r2)
    msg2  = (data2 or {}).get("detail", r2.text[:80])
    resultado(False, "lento", r2.status_code, gw2, ms2, msg2)


# ─── Resumen final ───────────────────────────────────────────

async def resumen():
    encabezado("Resumen del sistema tras la demo")
    async with httpx.AsyncClient(timeout=10.0) as http:
        r = await http.get(f"{STATS_URL}/stats/overview")
        if r.status_code != 200:
            print("  No se pudo obtener stats.")
            return
        ov = r.json()
        print(f"  Requests totales     : {ov['total_requests']}")
        print(f"  Requests últimas 24h : {ov['requests_last_24h']}")
        print(f"  Servicios activos    : {ov['active_services']}")
        print(f"  Clientes activos     : {ov['active_clients']}")
        print(f"  Errores totales      : {ov['total_errors']}")
        print(f"  Avg respuesta        : {ov['avg_response_time_ms']}ms")

        r2 = await http.get(f"{STATS_URL}/stats/gateways")
        if r2.status_code == 200 and r2.json():
            print("\n  Distribución de carga:")
            gws   = r2.json()
            total = sum(g["requests"] for g in gws)
            for g in gws:
                pct = g["requests"] / total * 100 if total else 0
                bar = "█" * int(pct / 5)
                print(f"    {g['instance']:20s} {bar:12s} {g['requests']} req ({pct:.0f}%)")

        r3 = await http.get(f"{STATS_URL}/stats/services")
        if r3.status_code == 200:
            print("\n  Uso por servicio:")
            for s in r3.json():
                if s["total_requests"] > 0:
                    print(f"    {s['service_name']:15s} {s['total_requests']:4d} req  "
                          f"errores={s['error_count']}  avg={s['avg_response_ms']}ms")

    print(f"\n  Dashboard en tiempo real → http://localhost:8080/dashboard\n")


# ─── Main ────────────────────────────────────────────────────

async def main():
    print("\n" + "="*60)
    print("  DEMO MULTI-CLIENTE — Sistema Distribuido")
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("="*60)

    # 1. Registrar clientes y permisos
    await registrar_clientes()
    await registrar_servicio_lento()

    # 2. Ejecutar todos los clientes de forma concurrente
    encabezado("Iniciando clientes concurrentes")
    print("  Todos los clientes harán sus requests en paralelo\n")

    async with httpx.AsyncClient(timeout=20.0) as client:
        await asyncio.gather(
            meteosur(client),
            menteclara(client),
            netscan(client),
            agentdetect(client),
            echotest(client),
        )

    # 3. Casos especiales (secuenciales para mejor legibilidad)
    async with httpx.AsyncClient(timeout=30.0) as client:
        await caso_sin_permiso(client)
        await caso_timeout(client)

    # 4. Resumen
    await resumen()


if __name__ == "__main__":
    asyncio.run(main())
