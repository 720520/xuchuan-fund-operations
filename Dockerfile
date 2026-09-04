FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 xuchuan && useradd --uid 10001 --gid 10001 --no-create-home xuchuan
COPY backend/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock
COPY backend/ /app/backend/
RUN pip install --no-cache-dir --no-deps ./backend && mkdir -p /data/archive && chown -R 10001:10001 /data
COPY --from=frontend /frontend/dist/ /app/frontend/dist/
ENV PYTHONPATH=/app/backend
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
