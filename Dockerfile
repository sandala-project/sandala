# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS ui-builder

WORKDIR /src

COPY admin-ui/package.json admin-ui/package-lock.json ./admin-ui/
WORKDIR /src/admin-ui
RUN npm ci

WORKDIR /src
COPY admin-ui ./admin-ui
COPY sandala ./sandala
RUN npm run build --prefix admin-ui


FROM python:3.11-slim-bookworm AS wheel-builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /src

COPY pyproject.toml README.md LICENSE ./
COPY sandala ./sandala
COPY --from=ui-builder /src/sandala/admin_ui_dist ./sandala/admin_ui_dist

# The official image supports both local and S3-compatible asset storage.
RUN python -m pip wheel --wheel-dir /wheels ".[s3]" "gunicorn>=23.0.0"


FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    SANDALA_HOST=0.0.0.0 \
    SANDALA_PORT=3000 \
    SANDALA_ASSET_LOCAL_ROOT=/var/lib/sandala/assets \
    GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=4

RUN groupadd --system sandala \
    && useradd --system --gid sandala --create-home --home-dir /app sandala \
    && install --directory --owner=sandala --group=sandala /var/lib/sandala/assets

COPY --from=wheel-builder /wheels /wheels
RUN python -m pip install --no-index --find-links=/wheels /wheels/*.whl \
    && rm -rf /wheels

WORKDIR /app
USER sandala

VOLUME ["/var/lib/sandala/assets"]
EXPOSE 3000

# Bootstrap runs once before Gunicorn forks workers. This prevents concurrent
# first-time initialization of the users module by multiple workers.
CMD ["sh", "-c", "python -c 'from sandala.bootstrap import build_container; build_container()' && exec gunicorn --bind \"${SANDALA_HOST}:${SANDALA_PORT}\" --workers \"${GUNICORN_WORKERS}\" --threads \"${GUNICORN_THREADS}\" --access-logfile - --error-logfile - 'sandala.api.app:create_app()'"]
