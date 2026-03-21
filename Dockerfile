FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    wireguard-tools \
    iptables \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY config.example.yaml ./

# Bot runs as non-root; WG and iptables need to be run on host or with privilege
# This image is for the bot only. WireGuard typically runs on the host.
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "src.main"]
