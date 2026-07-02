FROM python:3.12-slim

WORKDIR /app

COPY service_manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY service_manager/ /app/service_manager/
COPY shared/ /app/shared/

WORKDIR /app/service_manager

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
