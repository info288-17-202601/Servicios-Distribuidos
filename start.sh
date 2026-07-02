#!/usr/bin/env bash
# ============================================================
# start.sh — Levanta todo el sistema distribuido
# ============================================================
set -e

echo ""
echo "┌────────────────────────────────────────────────┐"
echo "│  Sistema Distribuido — Jinetes del Apocalipsis │"
echo "└────────────────────────────────────────────────┘"
echo ""

# 1. Construir y levantar contenedores
echo "→ Levantando contenedores con Docker Compose..."
docker compose up --build -d

# 2. Esperar que la BD esté lista
echo "→ Esperando base de datos PostgreSQL..."
until docker compose exec postgres pg_isready -U admin -d distributed_sys > /dev/null 2>&1; do
  sleep 1
done
echo "  ✓ PostgreSQL listo"

# 3. Esperar servicios
echo "→ Esperando microservicios..."
sleep 8

echo ""
echo "✓ Sistema levantado exitosamente."
echo ""
echo "  Endpoints disponibles:"
echo "  ┌─────────────────────────────────────────────────────"
echo "  │ API Gateway (LB)     → http://localhost:80"
echo "  │ Service Manager      → http://localhost:8001/docs"
echo "  │ Stats Service        → http://localhost:8002/docs"
echo "  │ Monitor Dashboard    → http://localhost:8080/dashboard"
echo "  └─────────────────────────────────────────────────────"
echo ""
echo "  Clientes de prueba:"
echo "  ┌─────────────────────────────────────────────────────"
echo "  │ pip install httpx"
echo "  │ python clients/demo_client/client.py"
echo "  │ python clients/demo_client2/client.py"
echo "  └─────────────────────────────────────────────────────"
echo ""
echo "  Request de ejemplo:"
echo "  curl -H 'X-API-Key: testclient-key-001' http://localhost/api/quotes"
echo ""
