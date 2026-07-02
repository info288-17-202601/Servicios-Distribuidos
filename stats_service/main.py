"""
Stats Service — Monitoreo, métricas y recolección de uso.
"""
import asyncio
import os
import sys
sys.path.insert(0, "/app")
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, time

from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from sqlalchemy.orm import selectinload

from shared.database import get_db, init_db, AsyncSessionLocal
from shared.models import UsageLog, MetricsHourly, Service, Client


# ── Background task ──────────────────────────────────────────

async def aggregate_metrics_loop():
    await asyncio.sleep(10)
    while True:
        try:
            async with AsyncSessionLocal() as db:
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
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    asyncio.create_task(aggregate_metrics_loop())
    yield


# ── Schemas ──────────────────────────────────────────────────

class UsageEvent(BaseModel):
    service_id:       int | None = None
    status_code:      int
    response_time_ms: int


# ── App ──────────────────────────────────────────────────────

app = FastAPI(
    title="Stats Service",
    description="Monitoreo y estadísticas del sistema distribuido",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Endpoints ────────────────────────────────────────────────

@app.post("/internal/ingest", status_code=202)
async def ingest_event(event: UsageEvent):
    return {"accepted": True}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "stats_service", "timestamp": datetime.utcnow().isoformat()}


@app.get("/stats/overview")
async def overview(db: AsyncSession = Depends(get_db)):
    total_req = await db.execute(select(func.count()).select_from(UsageLog))
    total_svc = await db.execute(select(func.count()).select_from(Service).where(Service.is_active == True))
    total_cli = await db.execute(select(func.count()).select_from(Client).where(Client.is_active == True))
    errors    = await db.execute(select(func.count()).select_from(UsageLog).where(UsageLog.status_code >= 400))
    avg_resp  = await db.execute(select(func.avg(UsageLog.response_time_ms)).select_from(UsageLog))
    last_24h  = datetime.utcnow() - timedelta(hours=24)
    req_24h   = await db.execute(select(func.count()).select_from(UsageLog).where(UsageLog.requested_at >= last_24h))
    return {
        "total_requests":       total_req.scalar() or 0,
        "requests_last_24h":    req_24h.scalar() or 0,
        "active_services":      total_svc.scalar() or 0,
        "active_clients":       total_cli.scalar() or 0,
        "total_errors":         errors.scalar() or 0,
        "avg_response_time_ms": round(float(avg_resp.scalar() or 0), 2),
    }


@app.get("/stats/services")
async def stats_by_service(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT
            s.id,
            s.name,
            COUNT(ul.id)                                           AS total_requests,
            SUM(CASE WHEN ul.status_code < 400 THEN 1 ELSE 0 END) AS success_count,
            SUM(CASE WHEN ul.status_code >= 400 THEN 1 ELSE 0 END) AS error_count,
            ROUND(AVG(ul.response_time_ms)::numeric, 2)            AS avg_response_ms,
            MAX(ul.requested_at)                                   AS last_request
        FROM services s
        LEFT JOIN usage_logs ul ON s.id = ul.service_id
        GROUP BY s.id, s.name
        ORDER BY total_requests DESC
    """))
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
        for r in result.fetchall()
    ]


@app.get("/stats/clients")
async def stats_by_client(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT
            c.id, c.name, c.email,
            COUNT(ul.id)         AS total_requests,
            MAX(ul.requested_at) AS last_request
        FROM clients c
        LEFT JOIN usage_logs ul ON c.id = ul.client_id
        GROUP BY c.id, c.name, c.email
        ORDER BY total_requests DESC
    """))
    return [
        {
            "client_id":      r.id,
            "client_name":    r.name,
            "client_email":   r.email,
            "total_requests": r.total_requests or 0,
            "last_request":   r.last_request.isoformat() if r.last_request else None,
        }
        for r in result.fetchall()
    ]


@app.get("/stats/recent-logs")
async def recent_logs(
    page:  int = Query(1,  ge=1),
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Logs de hoy paginados. El campo correcto en el modelo es request_method."""
    now           = datetime.utcnow()
    start_of_day  = datetime.combine(now.date(), time.min)
    offset        = (page - 1) * limit

    try:
        # Total de hoy
        total_result = await db.execute(
            select(func.count())
            .select_from(UsageLog)
            .where(UsageLog.requested_at >= start_of_day)
        )
        total = total_result.scalar() or 0

        # Logs paginados con relaciones cargadas explícitamente
        result = await db.execute(
            select(UsageLog)
            .options(
                selectinload(UsageLog.client),
                selectinload(UsageLog.service),
            )
            .where(UsageLog.requested_at >= start_of_day)
            .order_by(UsageLog.requested_at.desc())
            .offset(offset)
            .limit(limit)
        )
        logs = result.scalars().all()

        return {
            "data": [
                {
                    "requested_at":     l.requested_at.isoformat(),
                    "client_id":        l.client_id,
                    "client":           l.client.name  if l.client  else "anónimo",
                    "service":          l.service.name if l.service else str(l.service_id),
                    "gateway_instance": l.gateway_instance,
                    "method":           l.request_method,   # ← nombre correcto del campo
                    "status_code":      l.status_code,
                    "response_time_ms": l.response_time_ms,
                    "client_ip":        l.client_ip,
                }
                for l in logs
            ],
            "total": total,
            "page":  page,
            "limit": limit,
        }

    except Exception as e:
        print(f"[recent-logs ERROR] {e}")
        return {"data": [], "total": 0, "page": page, "limit": limit}


@app.get("/stats/hourly/{service_id}")
async def hourly_metrics(
    service_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    since  = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(MetricsHourly)
        .where(MetricsHourly.service_id == service_id, MetricsHourly.hour_bucket >= since)
        .order_by(MetricsHourly.hour_bucket)
    )
    return [
        {
            "hour":            r.hour_bucket.isoformat(),
            "total_requests":  r.total_requests,
            "success_count":   r.success_count,
            "error_count":     r.error_count,
            "avg_response_ms": round(r.avg_response_ms, 2),
        }
        for r in result.scalars().all()
    ]


@app.get("/stats/gateways")
async def gateway_distribution(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT gateway_instance, COUNT(*) AS requests
        FROM usage_logs
        WHERE gateway_instance IS NOT NULL
        GROUP BY gateway_instance
        ORDER BY requests DESC
    """))
    return [{"instance": r.gateway_instance, "requests": r.requests} for r in result.fetchall()]


# ── Dashboard ────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
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
  header{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 32px;display:flex;align-items:center;gap:16px}
  .logo{font-size:20px;font-weight:800;color:var(--accent);letter-spacing:-0.5px}
  .badge{background:var(--accent)22;color:var(--accent);border:1px solid var(--accent)44;border-radius:4px;padding:2px 8px;font-size:12px;font-family:'JetBrains Mono',monospace}
  .refresh-btn{background:transparent;border:1px solid var(--border);color:var(--muted);padding:6px 16px;border-radius:6px;cursor:pointer;font-family:'Syne',sans-serif;font-size:13px;transition:all .2s}
  .refresh-btn:hover{border-color:var(--accent);color:var(--accent)}
  .ml-auto{margin-left:auto}
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
  .pagination{display:flex;justify-content:space-between;align-items:center;margin-top:14px}
  .page-info{color:var(--muted);font-family:'JetBrains Mono',monospace;font-size:12px}
</style>
</head>
<body>
<header>
  <span class="logo">⬡ API GATEWAY MONITOR</span>
  <span class="badge">Sistema Distribuido</span>
  <button class="refresh-btn ml-auto" onclick="loadAll()">↻ Actualizar</button>
</header>

<div class="container">

  <div class="grid-4" id="overview-cards">
    <div class="card"><div class="card-title">Requests Totales</div><div class="card-value accent">—</div></div>
    <div class="card"><div class="card-title">Últimas 24h</div><div class="card-value green">—</div></div>
    <div class="card"><div class="card-title">Tasa de Error</div><div class="card-value red">—</div></div>
    <div class="card"><div class="card-title">Resp. Promedio</div><div class="card-value yellow">—</div></div>
  </div>

  <div class="grid-2">
    <div class="card">
      <div class="section-title">Distribución de Carga por Gateway</div>
      <div id="gateway-dist" class="loading">Cargando...</div>
    </div>
    <div class="card">
      <div class="section-title">Uso por Servicio</div>
      <table>
        <thead><tr><th>Servicio</th><th>Requests</th><th>Errores</th><th>Avg ms</th></tr></thead>
        <tbody id="svc-table"><tr><td colspan="4" class="loading">Cargando...</td></tr></tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <div class="section-title">Logs de Hoy</div>
    <table>
      <thead>
        <tr>
          <th>Fecha y Hora</th>
          <th>ID Cliente</th>
          <th>Cliente</th>
          <th>Servicio</th>
          <th>Gateway</th>
          <th>Método</th>
          <th>Status</th>
          <th>Resultado</th>
          <th>Resp ms</th>
          <th>IP</th>
        </tr>
      </thead>
      <tbody id="logs-table">
        <tr><td colspan="10" class="loading">Cargando...</td></tr>
      </tbody>
    </table>
    <div class="pagination">
      <button class="refresh-btn" onclick="changePage(-1)">← Anterior</button>
      <span class="page-info" id="page-info">—</span>
      <button class="refresh-btn" onclick="changePage(1)">Siguiente →</button>
    </div>
  </div>

</div>

<script>
  let currentPage = 1;
  const PAGE_SIZE = 30;

  async function fetchJSON(url) {
    try {
      const r = await fetch(url);
      return r.json();
    } catch {
      return null;
    }
  }

  function statusClass(code) {
    if (code < 400) return 's2xx';
    if (code < 500) return 's4xx';
    return 's5xx';
  }

  function statusMessage(code) {
    const map = {
      200: 'OK', 201: 'Creado', 400: 'Solicitud inválida',
      401: 'No autenticado', 403: 'Sin permisos', 404: 'No encontrado',
      500: 'Error interno', 502: 'Bad Gateway',
      503: 'Circuit Breaker', 504: 'Timeout',
    };
    return map[code] || '-';
  }

  function changePage(delta) {
    const next = currentPage + delta;
    if (next < 1) return;
    currentPage = next;
    loadAll();
  }

  async function loadAll() {
    const [ov, svcs, logsRes, gws] = await Promise.all([
      fetchJSON('/stats/overview'),
      fetchJSON('/stats/services'),
      fetchJSON(`/stats/recent-logs?page=${currentPage}&limit=${PAGE_SIZE}`),
      fetchJSON('/stats/gateways'),
    ]);

    // Overview cards
    if (ov) {
      const errRate = ov.total_requests > 0
        ? ((ov.total_errors / ov.total_requests) * 100).toFixed(1)
        : '0.0';
      document.getElementById('overview-cards').innerHTML = `
        <div class="card"><div class="card-title">Requests Totales</div>
          <div class="card-value accent">${ov.total_requests.toLocaleString()}</div>
          <div class="card-sub">${ov.active_services} servicios activos</div></div>
        <div class="card"><div class="card-title">Últimas 24h</div>
          <div class="card-value green">${ov.requests_last_24h.toLocaleString()}</div>
          <div class="card-sub">${ov.active_clients} clientes activos</div></div>
        <div class="card"><div class="card-title">Tasa de Error</div>
          <div class="card-value red">${errRate}%</div>
          <div class="card-sub">${ov.total_errors} errores totales</div></div>
        <div class="card"><div class="card-title">Resp. Promedio</div>
          <div class="card-value yellow">${ov.avg_response_time_ms}ms</div>
          <div class="card-sub">todos los servicios</div></div>
      `;
    }

    // Gateway distribution
    if (gws && gws.length > 0) {
      const total = gws.reduce((a, g) => a + g.requests, 0);
      document.getElementById('gateway-dist').innerHTML = gws.map(g => `
        <div class="instance-bar">
          <span style="width:90px;font-size:12px;font-family:monospace;color:var(--muted)">${g.instance}</span>
          <div class="bar" style="width:${Math.max(4, (g.requests / total) * 100)}%"></div>
          <span style="font-size:12px;color:var(--accent);font-family:monospace">${g.requests}</span>
        </div>
      `).join('');
    } else {
      document.getElementById('gateway-dist').innerHTML =
        '<span class="loading">Sin datos — haz requests al gateway</span>';
    }

    // Services table
    if (svcs) {
      document.getElementById('svc-table').innerHTML = svcs.length
        ? svcs.map(s => `
          <tr>
            <td style="color:var(--text)">${s.service_name}</td>
            <td>${s.total_requests}</td>
            <td style="color:${s.error_count > 0 ? 'var(--red)' : 'var(--green)'}">${s.error_count}</td>
            <td>${s.avg_response_ms}</td>
          </tr>`).join('')
        : '<tr><td colspan="4" class="loading">Sin datos</td></tr>';
    }

    // Logs table
    if (logsRes) {
      const logs  = logsRes.data  || [];
      const total = logsRes.total || 0;
      const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

      document.getElementById('page-info').innerText =
        `Página ${currentPage} de ${totalPages} • ${total} logs hoy`;

      // Si la página pedida supera el total, volver a la última
      if (currentPage > totalPages) {
        currentPage = totalPages;
        loadAll();
        return;
      }

      document.getElementById('logs-table').innerHTML = logs.length
        ? logs.map(l => `
          <tr>
            <td style="color:var(--muted)">${new Date(l.requested_at + 'Z').toLocaleString('es-CL', { timeZone: 'America/Santiago' })}</td>
            <td>${l.client_id ?? '—'}</td>
            <td>${l.client}</td>
            <td>${l.service}</td>
            <td style="color:var(--accent)">${l.gateway_instance || '?'}</td>
            <td>${l.method || '?'}</td>
            <td><span class="status ${statusClass(l.status_code)}">${l.status_code}</span></td>
            <td>${statusMessage(l.status_code)}</td>
            <td>${l.response_time_ms}ms</td>
            <td style="color:var(--muted)">${l.client_ip}</td>
          </tr>`).join('')
        : '<tr><td colspan="10" class="loading">Sin logs hoy todavía</td></tr>';
    }
  }

  loadAll();
  setInterval(loadAll, 10000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("SERVICE_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVICE_PORT", 8002)),
        reload=False,
    )
