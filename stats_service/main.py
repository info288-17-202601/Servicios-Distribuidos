"""
Stats Service — Monitoreo, métricas y recolección de uso.

Funcionalidades:
  • Recibir eventos de uso del gateway (procesamiento asíncrono)
  • Agregar métricas por hora (background task)
  • Proveer dashboard de estadísticas en tiempo real
  • Consultas de métricas: por servicio, por cliente, por rango de fechas
  • Estadísticas globales del sistema
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

sys.path.insert(0, "/app")
from shared.database import get_db, init_db, AsyncSessionLocal
from shared.models import UsageLog, MetricsHourly, Service, Client

# Background task: agrega métricas cada 5 minutos

async def aggregate_metrics_loop():
    """Tarea de fondo que agrega métricas por hora cada 5 minutos."""
    await asyncio.sleep(10)  # esperar que la BD esté lista
    while True:
        try:
            async with AsyncSessionLocal() as db:
                # Agrupar logs por servicio y hora
                result = await db.execute(text("""
                    SELECT
                        service_id,
                        date_trunc('hour', requested_at) AS hour_bucket,
                        COUNT(*)                          AS total_requests,
                        SUM(CASE WHEN status_code < 400 THEN 1 ELSE 0 END) AS success_count,
                        SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_count,
                        AVG(response_time_ms)             AS avg_response_ms
                    FROM usage_logs
                    WHERE service_id IS NOT NULL
                      AND requested_at >= NOW() - INTERVAL '2 hours'
                    GROUP BY service_id, date_trunc('hour', requested_at)
                """))
                rows = result.fetchall()
                for row in rows:
                    # Upsert en metrics_hourly
                    await db.execute(text("""
                        INSERT INTO metrics_hourly
                            (service_id, hour_bucket, total_requests, success_count, error_count, avg_response_ms)
                        VALUES
                            (:service_id, :hour_bucket, :total, :success, :error, :avg_ms)
                        ON CONFLICT (service_id, hour_bucket) DO UPDATE SET
                            total_requests  = EXCLUDED.total_requests,
                            success_count   = EXCLUDED.success_count,
                            error_count     = EXCLUDED.error_count,
                            avg_response_ms = EXCLUDED.avg_response_ms
                    """), {
                        "service_id":  row.service_id,
                        "hour_bucket": row.hour_bucket,
                        "total":       row.total_requests,
                        "success":     row.success_count,
                        "error":       row.error_count,
                        "avg_ms":      float(row.avg_response_ms or 0),
                    })
                await db.commit()
        except Exception as e:
            print(f"[aggregate_metrics_loop] Error: {e}")
        await asyncio.sleep(300)  # cada 5 minutos


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    asyncio.create_task(aggregate_metrics_loop())
    yield

# Schemas

class UsageEvent(BaseModel):
    service_id:      int | None = None
    status_code:     int
    response_time_ms: int


app = FastAPI(
    title="Stats Service",
    description="Monitoreo y estadísticas del sistema distribuido",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Ingestión interna (llamada por el gateway)

@app.post("/internal/ingest", status_code=202)
async def ingest_event(event: UsageEvent):
    """
    Recibe eventos del gateway de forma asíncrona.
    El log ya fue guardado por el gateway; aquí solo actualizamos
    métricas en memoria/caché si fuera necesario.
    """
    return {"accepted": True}

# Estadísticas globales

@app.get("/health")
async def health():
    return {"status": "ok", "service": "stats_service", "timestamp": datetime.utcnow().isoformat()}


@app.get("/stats/overview")
async def overview(db: AsyncSession = Depends(get_db)):
    """Resumen global del sistema."""
    total_req  = await db.execute(select(func.count()).select_from(UsageLog))
    total_svc  = await db.execute(select(func.count()).select_from(Service).where(Service.is_active == True))
    total_cli  = await db.execute(select(func.count()).select_from(Client).where(Client.is_active == True))
    errors     = await db.execute(select(func.count()).select_from(UsageLog).where(UsageLog.status_code >= 400))
    avg_resp   = await db.execute(select(func.avg(UsageLog.response_time_ms)).select_from(UsageLog))

    last_24h = datetime.utcnow() - timedelta(hours=24)
    req_24h  = await db.execute(select(func.count()).select_from(UsageLog).where(UsageLog.requested_at >= last_24h))

    return {
        "total_requests":      total_req.scalar() or 0,
        "requests_last_24h":   req_24h.scalar() or 0,
        "active_services":     total_svc.scalar() or 0,
        "active_clients":      total_cli.scalar() or 0,
        "total_errors":        errors.scalar() or 0,
        "avg_response_time_ms": round(float(avg_resp.scalar() or 0), 2),
    }


@app.get("/stats/services")
async def stats_by_service(db: AsyncSession = Depends(get_db)):
    """Estadísticas de uso desglosadas por servicio."""
    result = await db.execute(text("""
        SELECT
            s.id,
            s.name,
            COUNT(ul.id)                                         AS total_requests,
            SUM(CASE WHEN ul.status_code < 400 THEN 1 ELSE 0 END) AS success_count,
            SUM(CASE WHEN ul.status_code >= 400 THEN 1 ELSE 0 END) AS error_count,
            ROUND(AVG(ul.response_time_ms)::numeric, 2)          AS avg_response_ms,
            MAX(ul.requested_at)                                 AS last_request
        FROM services s
        LEFT JOIN usage_logs ul ON s.id = ul.service_id
        GROUP BY s.id, s.name
        ORDER BY total_requests DESC
    """))
    rows = result.fetchall()
    return [
        {
            "service_id":      r.id,
            "service_name":    r.name,
            "total_requests":  r.total_requests or 0,
            "success_count":   r.success_count or 0,
            "error_count":     r.error_count or 0,
            "avg_response_ms": float(r.avg_response_ms or 0),
            "last_request":    r.last_request.isoformat() if r.last_request else None,
        }
        for r in rows
    ]


@app.get("/stats/clients")
async def stats_by_client(db: AsyncSession = Depends(get_db)):
    """Estadísticas de uso desglosadas por cliente."""
    result = await db.execute(text("""
        SELECT
            c.id,
            c.name,
            c.email,
            COUNT(ul.id)    AS total_requests,
            MAX(ul.requested_at) AS last_request
        FROM clients c
        LEFT JOIN usage_logs ul ON c.id = ul.client_id
        GROUP BY c.id, c.name, c.email
        ORDER BY total_requests DESC
    """))
    rows = result.fetchall()
    return [
        {
            "client_id":      r.id,
            "client_name":    r.name,
            "client_email":   r.email,
            "total_requests": r.total_requests or 0,
            "last_request":   r.last_request.isoformat() if r.last_request else None,
        }
        for r in rows
    ]


@app.get("/stats/recent-logs")
async def recent_logs(
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Últimos N logs de uso del sistema."""
    result = await db.execute(text("""
        SELECT
            ul.id,
            ul.client_id,
            c.name        AS client_name,
            s.name        AS service_name,
            ul.gateway_instance,
            ul.request_method,
            ul.status_code,
            ul.response_time_ms,
            ul.client_ip,
            ul.requested_at
        FROM usage_logs ul
        LEFT JOIN clients  c ON ul.client_id  = c.id
        LEFT JOIN services s ON ul.service_id = s.id
        ORDER BY ul.requested_at DESC
        LIMIT :limit
    """), {"limit": limit})
    rows = result.fetchall()
    return [
        {
            "id":               r.id,
            "client_id":        r.client_id,
            "client":           r.client_name or "anónimo",
            "service":          r.service_name or "?",
            "gateway_instance": r.gateway_instance,
            "method":           r.request_method,
            "status_code":      r.status_code,
            "response_time_ms": r.response_time_ms,
            "client_ip":        r.client_ip,
            "requested_at":     r.requested_at.isoformat() if r.requested_at else None,
        }
        for r in rows
    ]


@app.get("/stats/hourly/{service_id}")
async def hourly_metrics(
    service_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """Métricas horarias de un servicio específico."""
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(MetricsHourly)
        .where(MetricsHourly.service_id == service_id, MetricsHourly.hour_bucket >= since)
        .order_by(MetricsHourly.hour_bucket)
    )
    rows = result.scalars().all()
    return [
        {
            "hour":            r.hour_bucket.isoformat(),
            "total_requests":  r.total_requests,
            "success_count":   r.success_count,
            "error_count":     r.error_count,
            "avg_response_ms": round(r.avg_response_ms, 2),
        }
        for r in rows
    ]


@app.get("/stats/gateways")
async def gateway_distribution(db: AsyncSession = Depends(get_db)):
    """Distribución de requests por instancia del gateway (balanceo de carga)."""
    result = await db.execute(text("""
        SELECT gateway_instance, COUNT(*) AS requests
        FROM usage_logs
        WHERE gateway_instance IS NOT NULL
        GROUP BY gateway_instance
        ORDER BY requests DESC
    """))
    rows = result.fetchall()
    return [{"instance": r.gateway_instance, "requests": r.requests} for r in rows]


# Dashboard HTML integrado (visualización rápida)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Dashboard de monitoreo en tiempo real."""
    return HTMLResponse(content=DASHBOARD_HTML)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Monitor — Sistema Distribuido</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap');
  :root{--bg:#0a0e1a;--surface:#111827;--border:#1e2d45;--accent:#00d4ff;--green:#00ff9d;--red:#ff4757;--yellow:#ffd32a;--text:#e2e8f0;--muted:#64748b}
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Syne',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
  .mono{font-family:'JetBrains Mono',monospace}
  header{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 32px;display:flex;align-items:center;gap:16px}
  .logo{font-size:20px;font-weight:800;color:var(--accent);letter-spacing:-0.5px}
  .badge{background:var(--accent)22;color:var(--accent);border:1px solid var(--accent)44;border-radius:4px;padding:2px 8px;font-size:12px;font-family:'JetBrains Mono',monospace}
  .refresh-btn{margin-left:auto;background:transparent;border:1px solid var(--border);color:var(--muted);padding:6px 16px;border-radius:6px;cursor:pointer;font-family:'Syne',sans-serif;font-size:13px;transition:all .2s}
  .refresh-btn:hover{border-color:var(--accent);color:var(--accent)}
  .container{max-width:1400px;margin:0 auto;padding:32px}
  .grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:32px}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px}
  .card-title{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:8px}
  .card-value{font-size:36px;font-weight:800;font-family:'JetBrains Mono',monospace}
  .card-sub{font-size:12px;color:var(--muted);margin-top:4px}
  .accent{color:var(--accent)} .green{color:var(--green)} .red{color:var(--red)} .yellow{color:var(--yellow)}
  .grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:32px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th{text-align:left;padding:10px 12px;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);border-bottom:1px solid var(--border)}
  td{padding:10px 12px;border-bottom:1px solid var(--border)22;font-family:'JetBrains Mono',monospace}
  tr:hover td{background:#ffffff05}
  .status{display:inline-block;padding:2px 8px;border-radius:3px;font-size:11px}
  .s2xx{background:#00ff9d22;color:var(--green)} .s4xx{background:#ffd32a22;color:var(--yellow)} .s5xx{background:#ff475722;color:var(--red)}
  .instance-bar{display:flex;gap:8px;align-items:center;margin-bottom:8px}
  .bar{height:20px;border-radius:4px;background:var(--accent);transition:width .5s}
  .loading{color:var(--muted);font-family:'JetBrains Mono',monospace;font-size:13px}
  .section-title{font-size:16px;font-weight:700;margin-bottom:16px;color:var(--text)}
</style>
</head>
<body>
<header>
  <span class="logo">⬡ API GATEWAY MONITOR</span>
  <span class="badge">Sistema Distribuido</span>
  <button class="refresh-btn" onclick="loadAll()">↻ Actualizar</button>
</header>

<div class="container">
  <!-- Métricas globales -->
  <div class="grid-4" id="overview-cards">
    <div class="card"><div class="card-title">Requests Totales</div><div class="card-value accent loading">—</div></div>
    <div class="card"><div class="card-title">Últimas 24h</div><div class="card-value green loading">—</div></div>
    <div class="card"><div class="card-title">Tasa de Error</div><div class="card-value red loading">—</div></div>
    <div class="card"><div class="card-title">Resp. Promedio</div><div class="card-value yellow loading">—</div></div>
  </div>

  <div class="grid-2">
    <!-- Balanceo de carga por instancia -->
    <div class="card">
      <div class="section-title">Distribución de Carga por Gateway</div>
      <div id="gateway-dist" class="loading">Cargando...</div>
    </div>

    <!-- Servicios activos -->
    <div class="card">
      <div class="section-title">Uso por Servicio</div>
      <table><thead><tr><th>Servicio</th><th>Requests</th><th>Errores</th><th>Avg ms</th></tr></thead>
      <tbody id="svc-table"><tr><td colspan="4" class="loading">Cargando...</td></tr></tbody></table>
    </div>
  </div>

  <!-- Logs recientes -->
  <div class="card">
    <div class="section-title">Logs Recientes</div>
    <table>
      <thead><tr>
      <th>Fecha y hora</th>
      <th>ID Cliente</th>
      <th>Cliente</th>
      <th>Servicio</th>
      <th>Gateway</th>
      <th>Método</th>
      <th>Status</th>
      <th>Resultado</th>
      <th>Resp ms</th>
      <th>IP</th>
      </tr></thead>
      <tbody id="logs-table"><tr><td colspan="10" class="loading">Cargando...</td></tr></tbody>
    </table>
  </div>
</div>

<script>
const BASE = '';

async function fetchJSON(url){
  try{const r=await fetch(url);return r.json()}catch{return null}
}

function statusClass(code){
  if(code<400) return 's2xx';
  if(code<500) return 's4xx';
  return 's5xx';
}

function statusMessage(code){

    switch(code){

        case 200:
            return "OK";

        case 201:
            return "Creado";

        case 400:
            return "Solicitud inválida";

        case 401:
            return "No autenticado";

        case 403:
            return "Sin permisos";

        case 404:
            return "No encontrado";

        case 500:
            return "Error interno";

        case 502:
            return "Bad Gateway";

        case 503:
            return "Circuit Breaker";

        case 504:
            return "Timeout";

        default:
            return "-";
    }
}

async function loadAll(){
  const [ov, svcs, logs, gws] = await Promise.all([
    fetchJSON(BASE+'/stats/overview'),
    fetchJSON(BASE+'/stats/services'),
    fetchJSON(BASE+'/stats/recent-logs?limit=30'),
    fetchJSON(BASE+'/stats/gateways'),
  ]);

  // Overview cards
  if(ov){
    const errRate = ov.total_requests > 0 ? ((ov.total_errors/ov.total_requests)*100).toFixed(1) : '0.0';
    document.getElementById('overview-cards').innerHTML = `
      <div class="card"><div class="card-title">Requests Totales</div><div class="card-value accent">${ov.total_requests.toLocaleString()}</div><div class="card-sub">${ov.active_services} servicios activos</div></div>
      <div class="card"><div class="card-title">Últimas 24h</div><div class="card-value green">${ov.requests_last_24h.toLocaleString()}</div><div class="card-sub">${ov.active_clients} clientes activos</div></div>
      <div class="card"><div class="card-title">Tasa de Error</div><div class="card-value red">${errRate}%</div><div class="card-sub">${ov.total_errors} errores totales</div></div>
      <div class="card"><div class="card-title">Resp. Promedio</div><div class="card-value yellow">${ov.avg_response_time_ms}ms</div><div class="card-sub">todos los servicios</div></div>
    `;
  }

  // Gateway distribution
  if(gws && gws.length > 0){
    const total = gws.reduce((a,g)=>a+g.requests,0);
    document.getElementById('gateway-dist').innerHTML = gws.map(g=>`
      <div class="instance-bar">
        <span style="width:90px;font-size:12px;font-family:monospace;color:var(--muted)">${g.instance}</span>
        <div class="bar" style="width:${Math.max(4,(g.requests/total)*100)}%"></div>
        <span style="font-size:12px;color:var(--accent);font-family:monospace">${g.requests}</span>
      </div>
    `).join('');
  } else {
    document.getElementById('gateway-dist').innerHTML = '<span class="loading">Sin datos aún — haz requests al gateway</span>';
  }

  // Services table
  if(svcs){
    document.getElementById('svc-table').innerHTML = svcs.map(s=>`
      <tr>
        <td style="color:var(--text)">${s.service_name}</td>
        <td>${s.total_requests}</td>
        <td style="color:${s.error_count>0?'var(--red)':'var(--green)'}">${s.error_count}</td>
        <td>${s.avg_response_ms}</td>
      </tr>
    `).join('') || '<tr><td colspan="4" class="loading">Sin datos</td></tr>';
  }

  // Logs table
  if(logs){
    document.getElementById('logs-table').innerHTML = logs.map(l=>`
      <tr>
        <td style="color:var(--muted)">
        ${new Date(l.requested_at).toLocaleString('es-CL')}
        </td>
        <td>${l.client_id}</td>
        <td style="color:var(--text)">
            ${l.client}
        </td>
        <td>${l.service}</td>
        <td style="color:var(--accent)">${l.gateway_instance||'?'}</td>
        <td>${l.method}</td>
        <td><span class="status ${statusClass(l.status_code)}">${l.status_code}</span></td>
        <td>
        ${statusMessage(l.status_code)}
        </td>
        <td>${l.response_time_ms}ms</td>
        <td style="color:var(--muted)">${l.client_ip}</td>
      </tr>
    `).join('') || '<tr><td colspan="10" class="loading">Sin logs</td></tr>';
  }
}

loadAll();
setInterval(loadAll, 10000);  // auto-refresh cada 10s
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=os.getenv("SERVICE_HOST", "0.0.0.0"),
                port=int(os.getenv("SERVICE_PORT", 8002)), reload=False)
