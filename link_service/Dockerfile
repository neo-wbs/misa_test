FROM python:3.11-slim

WORKDIR /app

COPY link_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared ./shared
COPY . .

EXPOSE 8002

CMD ["uvicorn", "link_service.main:app", "--host", "0.0.0.0", "--port", "8002"]