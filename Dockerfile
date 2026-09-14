# Container image specification for Video Summarizer.
# Responsible for defining the reproducible runtime container for Hugging Face Spaces
# and Docker deployments, bundling Python 3.13, uv, ffmpeg, and application dependencies.
# Must not execute as root (UID 1000 required for Hugging Face Space security sandbox).
# Next: container-entrypoint.sh for runtime volume initialization.

FROM ghcr.io/astral-sh/uv:0.12.5 AS uv

FROM python:3.13-slim-trixie

ARG DEBIAN_FRONTEND=noninteractive

# Security and storage boundary: creates non-root user (UID 1000) required by
# Hugging Face Spaces, and prepares /data mount point for persistent NVMe storage.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 user \
    && mkdir -p /data /home/user/app \
    && chown -R user:user /data /home/user/app

COPY --from=uv /uv /uvx /bin/

ENV HOME=/home/user \
    PATH=/home/user/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

WORKDIR /home/user/app

COPY --chown=user:user pyproject.toml uv.lock ./

USER user

RUN uv sync --locked --no-dev --no-install-project

COPY --chown=user:user . .

RUN chmod 0755 container-entrypoint.sh

ENTRYPOINT ["/home/user/app/container-entrypoint.sh"]
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=7860", "--server.headless=true", "--browser.gatherUsageStats=false"]
