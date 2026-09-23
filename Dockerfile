FROM python:3.12-slim

# База SQLite лежит в /data: на хостинге туда монтируется постоянный диск, в docker compose — том
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/data/app.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ server/
COPY web/ web/
COPY data/events.json data/events.json

EXPOSE 3000
CMD ["sh", "-c", "python -m uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-3000}"]
