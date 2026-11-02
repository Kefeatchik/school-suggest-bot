# Универсальный образ: подходит для VPS, Railway, Render, Fly.io и др.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# База SQLite хранится тут — подключи сюда volume/disk, чтобы не терять данные
RUN mkdir -p /app/data
VOLUME ["/app/data"]

CMD ["python", "main.py"]
