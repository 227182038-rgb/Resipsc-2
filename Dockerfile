# resipsc v2.0.0 — deterministic build with pinned dependencies
# Build: docker build -t resipsc:2.0.0 .
# Run:   docker run -p 3000:3000 resipsc:2.0.0

FROM oven/bun:1.1 AS node-deps
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

FROM python:3.12-slim AS py-deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Python environment (with the DATABASE_URL/anndata shim)
COPY --from=py-deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY requirements.txt pyproject.toml ./

# Node environment
COPY --from=node-deps /app/node_modules ./node_modules
COPY --from=oven/bun:1.1 /usr/local/bin/bun /usr/local/bin/bun

# Application source
COPY resipsc ./resipsc
COPY scripts ./scripts
COPY src ./src
COPY public ./public
COPY package.json next.config.ts tsconfig.json components.json postcss.config.mjs ./
COPY paper ./paper
COPY results ./results
COPY db ./db
COPY data ./data

# SBOM is copied alongside (sbom.json)
COPY sbom.json ./

ENV NODE_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONWARNINGS=ignore \
    NEXT_TELEMETRY_DISABLED=1

# install the python package (no isolated build deps needed beyond setuptools)
RUN pip install --no-cache-dir --no-deps .

EXPOSE 3000
CMD ["bun", "run", "dev"]
