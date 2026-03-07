# Stage 1: Build SvelteKit frontend
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y gcc && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY app/ ./app/
COPY scripts/ ./scripts/

# Copy built frontend
COPY --from=frontend-build /frontend/build ./frontend/build

RUN mkdir -p /data/cache

EXPOSE 9117

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9117"]
