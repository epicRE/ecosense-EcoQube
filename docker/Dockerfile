FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir "paho-mqtt>=2.0"

COPY ecoqube-web2mqtt-server.py ./
COPY docker/entrypoint.sh ./

RUN mkdir -p /app/certs /app/data /app/www

EXPOSE 8443
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
