# syntax=docker/dockerfile:1
# Parameterized image for ALL Python microservices: one build, N services.
#   docker build --build-arg SERVICE=session-orchestrator -t ga/session-orchestrator .
# Service = directory under services/ whose pyproject declares [project.scripts].
# The launch target (pkg.module:fn) is read from that pyproject at build time and
# rendered into /entrypoint.py, so no per-service Dockerfile maintenance exists.
ARG BASE=python:3.12-slim
FROM ${BASE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/app/.venv

WORKDIR /opt/app
RUN pip install --no-cache-dir uv==0.7.*

ARG SERVICE=session-orchestrator

COPY . .
RUN PACKAGE=$(python -c "import tomllib; print(tomllib.load(open('services/${SERVICE}/pyproject.toml','rb'))['project']['name'])") && \
    ENTRY=$(python -c "import tomllib; s=tomllib.load(open('services/${SERVICE}/pyproject.toml','rb'))['project']['scripts']; print(next(iter(s.values())))") && \
    MOD=${ENTRY%:*} FN=${ENTRY##*:} && \
    printf 'import importlib\n_m = importlib.import_module("%s")\n_m.%s()\n' "$MOD" "$FN" > /entrypoint.py && \
    uv sync --frozen --package "$PACKAGE" && \
    uv run python -c "import uno_schemas, uno_shared, fastapi; print('deps ok')" && \
    uv run python -c "from uno_schemas.api import SERVICE_PORTS; open('/port.txt','w').write(str(SERVICE_PORTS['${SERVICE}']))" && \
    cat /entrypoint.py /port.txt

EXPOSE 8100
HEALTHCHECK --interval=15s --timeout=4s --start-period=20s --retries=5 \
  CMD uv run python -c "import httpx,sys; port=open('/port.txt').read().strip(); r=httpx.get(f'http://127.0.0.1:{port}/health',timeout=3); sys.exit(0 if r.status_code==200 else 1)"
CMD ["uv", "run", "/entrypoint.py"]
