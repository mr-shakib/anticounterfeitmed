# syntax=docker/dockerfile:1
#
# The signing service. It holds ML-DSA private keys and must have no database
# credentials, no object storage access and no public route -- see
# infra/docker-compose.prod.yml, where it sits on an internal-only network.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY libs/medcrypto /app/libs/medcrypto
COPY signer /app/signer
RUN pip install --no-cache-dir /app/libs/medcrypto /app/signer

# Keys are mounted at runtime from a secret store, never baked into the image.
RUN useradd --create-home --uid 10002 signer && mkdir -p /keys && chown signer /keys
USER signer

ENV SIGNER_KEYSTORE_PATH=/keys
CMD ["python", "-c", "print('signer image ready; transport not implemented (docs/02)')"]
