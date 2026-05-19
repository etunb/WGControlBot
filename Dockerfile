FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    wireguard-tools \
    iptables \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY scripts/setup-wg-isolation.sh ./scripts/setup-wg-isolation.sh
COPY docker-entrypoint.sh ./docker-entrypoint.sh
COPY config.example.yaml ./
RUN chmod +x /app/docker-entrypoint.sh /app/scripts/setup-wg-isolation.sh

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/app/docker-entrypoint.sh"]
