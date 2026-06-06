# Stage 1: Build SvelteKit frontend
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Build Python dependencies (C extensions need gcc + headers)
FROM python:3.12-alpine AS python-deps
RUN apk add --no-cache gcc musl-dev libuv-dev
COPY requirements.txt .
RUN python3 -m venv /venv && \
    /venv/bin/pip install --no-cache-dir -r requirements.txt

# Stage 3: Runtime
FROM python:3.12-alpine

WORKDIR /app

# Runtime dependency: libuv for uvloop
RUN apk add --no-cache libuv

# Copy Python virtual environment with all deps (no build tools)
COPY --from=python-deps /venv /venv
ENV PATH="/venv/bin:$PATH"

# Copy application code
COPY app/ ./app/
COPY scripts/ ./scripts/

# Copy built frontend
COPY --from=frontend-build /frontend/build ./frontend/build

RUN mkdir -p /data/cache

EXPOSE 9117

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9117"]
