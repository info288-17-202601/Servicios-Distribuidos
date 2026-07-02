FROM python:3.12-slim

WORKDIR /app

# El contexto de build es la raíz del proyecto (definido en docker-compose.yml)
# Por eso los paths son relativos a la raíz, no al subdirectorio
COPY api_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api_gateway/ /app/api_gateway/
COPY shared/ /app/shared/

WORKDIR /app/api_gateway

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
