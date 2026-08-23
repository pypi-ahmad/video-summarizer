FROM ghcr.io/astral-sh/uv:0.12.5 AS uv

FROM python:3.13-slim-trixie

ARG DEBIAN_FRONTEND=noninteractive

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
