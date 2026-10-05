FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/app

# Les dépendances d'abord : le cache de build survit aux changements de code.
COPY pyproject.toml ./
RUN pip install --no-cache-dir . && pip uninstall -y awtrixng-mgr

COPY alembic.ini docker-entrypoint.py ./
COPY app ./app

RUN useradd --system --uid 10001 --create-home awtrixng-mgr \
 && mkdir -p /data && chown -R awtrixng-mgr:awtrixng-mgr /data /srv/app \
 && chmod +x /srv/app/docker-entrypoint.py

# Pas de directive USER : /data est un bind mount dont l'appartenance vient de
# l'hôte. L'entrypoint démarre en root le temps de l'ajuster, puis abandonne
# ses privilèges. Le serveur tourne en awtrixng-mgr (uid 10001), jamais en root.
# Voir ADR-011.

ENV AWTRIXNG_DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

ENTRYPOINT ["/srv/app/docker-entrypoint.py"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
