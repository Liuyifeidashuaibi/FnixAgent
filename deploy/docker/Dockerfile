# FnixAgent production image
FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e . || pip install --no-cache-dir .

COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV SERVICE_ENV=production
ENV SERVICE_DEBUG=false
ENV FNIXAGENT_MODE=legacy

EXPOSE 8000

CMD ["python", "-m", "fnixagent.main", "serve", "--host", "0.0.0.0", "--port", "8000", "--no-reload"]
