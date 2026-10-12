#!/bin/sh
set -eu

set -- --root /app/www "$@"

if [ -n "${MQTT_HOST:-}" ]; then
  set -- "$@" --mqtt-host "$MQTT_HOST" --mqtt-port "${MQTT_PORT:-1883}"
  if [ -n "${MQTT_USERNAME:-}" ]; then
    set -- "$@" --mqtt-username "$MQTT_USERNAME" --mqtt-password "${MQTT_PASSWORD:-}"
  fi
fi

if [ "${PUT_LOG:-on}" = "off" ]; then
  set -- "$@" --no-put-log
fi

exec python ecoqube-web2mqtt-server.py "$@"
