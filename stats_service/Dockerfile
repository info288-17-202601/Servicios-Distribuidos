FROM python:3.12-slim

WORKDIR /app

COPY stats_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY stats_service/ /app/stats_service/
COPY shared/ /app/shared/

WORKDIR /app/stats_service

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
