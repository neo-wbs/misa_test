FROM python:3.11-slim

WORKDIR /app

# requirements.txt ZUERST → Layer-Caching nutzen
# (pip install läuft nur neu wenn sich requirements.txt ändert)
COPY auth_service/requirements.txt .
COPY auth_service/requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY shared ./shared
COPY . .

EXPOSE 8001

CMD ["uvicorn", "auth_service.main:app", "--host", "0.0.0.0", "--port", "8001"]