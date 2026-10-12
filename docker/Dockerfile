FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir "paho-mqtt>=2.0"

COPY ecoqube-web2mqtt-server.py ./
COPY docker/entrypoint.sh ./

RUN groupadd -r -g 10001 user001 && useradd -r -u 10001 -g user001 user001
RUN mkdir -p /app/certs /app/data /app/www && chown -R user001:user001 /app/certs /app/data

EXPOSE 8443
USER user001

ENTRYPOINT ["sh", "/app/entrypoint.sh"]
