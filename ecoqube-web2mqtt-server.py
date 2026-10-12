#!/usr/bin/env python3
# Project https://github.com/epicRE/ecosense-EcoQube/
# Vibecoded by Github Copilot (2026) 
# Copyright (c) 2026 EpicRE. All rights reserved. 

"""HTTPS static file server with a self-signed certificate and request tracking."""
import argparse
import datetime
import functools
import http.server
import json
import re
import ssl
import subprocess
import sys
import threading
import urllib.parse
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

SERIAL_RE = re.compile(r"[A-Za-z0-9_-]+")
RADON_FIELDS = ("serial_number", "fw_version")
NUMERIC_FIELDS = ("radon_level", "radon_dou", "d_status", "d_type", "p_time", "c_factor")
# (topic key, Home Assistant name, value extractor, diagnostic)
SENSORS = (
    ("radon", "Radon", lambda r: r["radon_level"], False),
    ("status", "status", lambda r: r["d_status"], True),
    ("measurements_taken", "Measurements Taken", lambda r: r["p_time"] / 10, True),
    ("device_type", "Device Type", lambda r: r["d_type"], True),
    ("radon_dou", "Radon DOU", lambda r: r["radon_dou"], True),
    ("c_factor", "C Factor", lambda r: r["c_factor"], True),
)


def parse_reading(raw):
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("body is not a JSON object")
    missing = [f for f in RADON_FIELDS + NUMERIC_FIELDS if f not in data]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")
    if not SERIAL_RE.fullmatch(str(data["serial_number"])):
        raise ValueError("invalid serial_number")
    for field in NUMERIC_FIELDS:
        value = data[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field} must be a number")
    return data


def sensor_config(serial, fw, key, name, diagnostic):
    config = {
        "state_topic": f"homeassistant/sensor/{serial}/{key}/state",
        "unique_id": f"{serial}-{key}",
        "name": name,
        "device": {
            "identifiers": [serial],
            "name": f"Ecoqube {serial}",
            "manufacturer": "Ecosense",
            "model": "Ecoqube",
            "serial_number": serial,
            "sw_version": fw,
        },
    }
    if diagnostic:
        config["entity_category"] = "diagnostic"
    if key == "radon":
        config.update(unit_of_measurement="Bq/m³", state_class="measurement")
    return config


class MqttPublisher:
    def __init__(self, client):
        self.client = client
        self.lock = threading.Lock()
        self.configured = {}  # serial -> firmware version last announced

    def publish(self, reading):
        serial = str(reading["serial_number"])
        fw = str(reading["fw_version"])
        with self.lock:
            if self.configured.get(serial) != fw:
                for key, name, _, diagnostic in SENSORS:
                    payload = json.dumps(sensor_config(serial, fw, key, name, diagnostic))
                    self.client.publish(f"homeassistant/sensor/{serial}/{key}/config", payload, qos=1, retain=True)
                self.configured[serial] = fw
            for key, _, value, _ in SENSORS:
                self.client.publish(f"homeassistant/sensor/{serial}/{key}/state", str(value(reading)), qos=1)


class RequestTracker:
    def __init__(self, log_file=None):
        self.lock = threading.Lock()
        self.total = 0
        self.by_path = Counter()
        self.by_client = Counter()
        self.log_file = open(log_file, "a", encoding="utf-8") if log_file else None

    def record(self, client, method, path, status, agent):
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        line = f"[{stamp}] {client} {method} {path} -> {status} {agent}"
        with self.lock:
            self.total += 1
            self.by_path[path] += 1
            self.by_client[client] += 1
            print(f"#{self.total} {line}", flush=True)
            if self.log_file:
                self.log_file.write(line + "\n")
                self.log_file.flush()

    def summary(self):
        with self.lock:
            print(f"\nTotal requests: {self.total}")
            print("Top paths:")
            for path, count in self.by_path.most_common(10):
                print(f"  {count:6d}  {path}")
            print("Clients:")
            for client, count in self.by_client.most_common():
                print(f"  {count:6d}  {client}")


class TrackingHandler(http.server.SimpleHTTPRequestHandler):
    tracker = None
    data_dir = None
    put_lock = threading.Lock()
    publisher = None

    def setup(self):
        self.request.do_handshake()
        super().setup()

    def reject(self):
        self.send_error(404, "Not Found")

    do_GET = do_HEAD = reject

    def __getattr__(self, name):
        # Unknown methods would otherwise get 501 from the base class.
        if name.startswith("do_") and name != "do_PUT":
            return self.reject
        raise AttributeError(name)

    def log_request(self, code="-", size="-"):
        self.tracker.record(
            self.client_address[0],
            self.command or "-",
            ascii(self.path),
            code,
            ascii(self.headers.get("User-Agent", "-")),
        )

    def do_PUT(self):
        segments = [s for s in urllib.parse.urlsplit(self.path).path.split("/") if s]
        if not segments or not all(re.fullmatch(r"[A-Za-z0-9_-]+", s) for s in segments):
            self.send_error(400, "Invalid resource path")
            return
        length = self.headers.get("Content-Length")
        if length is None:
            self.send_error(411, "Content-Length required")
            return
        body = self.rfile.read(int(length))
        if self.data_dir is not None:
            entry = {
                "time": datetime.datetime.now().isoformat(timespec="seconds"),
                "client": self.client_address[0],
                "path": self.path,
                "body": body.decode("utf-8", errors="replace"),
            }
            with self.put_lock, open(self.data_dir / "put_log.jsonl", "a", encoding="utf-8") as log:
                log.write(json.dumps(entry) + "\n")
        if segments[-1] == "radon":
            try:
                reading = parse_reading(body)
            except ValueError as exc:
                self.send_error(400, f"Invalid radon payload: {exc}")
                return
            if self.publisher is not None:
                self.publisher.publish(reading)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format, *args):
        pass


class TLSServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    ssl_context = None

    def get_request(self):
        sock, addr = self.socket.accept()
        sock.settimeout(10)
        tls_sock = self.ssl_context.wrap_socket(
            sock, server_side=True, do_handshake_on_connect=False
        )
        return tls_sock, addr

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ssl.SSLError, OSError)):
            print(f"connection error from {client_address[0]}: {exc}", flush=True)
        else:
            super().handle_error(request, client_address)


def ensure_cert(cert, key):
    if cert.exists() and key.exists():
        return
    cert.parent.mkdir(parents=True, exist_ok=True)
    print(f"Generating self-signed certificate: {cert}")
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "365",
            "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--root", default=".", help="directory to serve")
    parser.add_argument("--cert", default=str(SCRIPT_DIR / "certs" / "cert.pem"))
    parser.add_argument("--key", default=str(SCRIPT_DIR / "certs" / "key.pem"))
    parser.add_argument("--log", help="also append requests to this file")
    parser.add_argument("--data-dir", default=str(SCRIPT_DIR / "data"), help="where PUT bodies are saved")
    parser.add_argument("--no-put-log", action="store_true", help="do not save PUT bodies to put_log.jsonl")
    parser.add_argument("--mqtt-host", help="publish radon readings to this MQTT broker")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--mqtt-username")
    parser.add_argument("--mqtt-password")
    args = parser.parse_args()

    cert, key = Path(args.cert), Path(args.key)
    try:
        ensure_cert(cert, key)
    except (OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f"Could not create certificate (is openssl installed?): {exc}")

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert, key)

    TrackingHandler.tracker = RequestTracker(args.log)
    TrackingHandler.data_dir = None if args.no_put_log else Path(args.data_dir)
    if TrackingHandler.data_dir is not None:
        TrackingHandler.data_dir.mkdir(parents=True, exist_ok=True)

    mqtt_client = None
    if args.mqtt_host:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            sys.exit("MQTT publishing needs paho-mqtt: pip install paho-mqtt")
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if args.mqtt_username:
            mqtt_client.username_pw_set(args.mqtt_username, args.mqtt_password)
        # Async so the server starts even if the broker is down; paho retries in the background.
        mqtt_client.connect_async(args.mqtt_host, args.mqtt_port)
        mqtt_client.loop_start()
        TrackingHandler.publisher = MqttPublisher(mqtt_client)

    handler = functools.partial(TrackingHandler, directory=args.root)
    server = TLSServer((args.host, args.port), handler)
    server.ssl_context = ctx

    print(f"Serving https://{args.host}:{args.port} from {Path(args.root).resolve()} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if mqtt_client is not None:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        TrackingHandler.tracker.summary()


if __name__ == "__main__":
    main()
