# Docker Setup

Run these from a terminal on the machine that will host the container.

**1. Get the repo**

```sh
git clone https://github.com/epicRE/ecosense-EcoQube.git
cd ecosense-EcoQube
```

If you already have a clone, update it instead:

```sh
cd ecosense-EcoQube
git fetch origin
git checkout main
git pull origin main
```

**2. Prepare the data and certificate folders**

The compose file mounts `../data` and `../certs`, so create them next to `docker`:

```sh
mkdir -p data certs
```

**3. Configure the environment**

```sh
cd docker
cp .env.example .env
```

Edit `.env` to set `MQTT_HOST` and related values (`MQTT_USERNAME`,`MQTT_PASSWORD`). Set `HOST_PORT=443`, you need to keep 443 as this is the port that the device connects to. 

**4. Validate and build**

```sh
docker compose config --quiet && echo "compose OK"
docker compose up -d --build
docker compose ps
docker compose logs -f
```

Watch the logs for `Serving https://0.0.0.0:8443`. If you see `Could not create certificate (is openssl installed?)`, the image lacks the `openssl` CLI. Generate the certificate on the host and place it in `certs`:

```sh
openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/key.pem -out certs/cert.pem -days 1825 -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

Then check the certificate paths that `ecoqube-web2mqtt-server.py` expects.

**5. Test the endpoint**

Replace localhost with your system's IP address. 

```sh
# Should return 404 (only PUT is allowed)
curl -k -i https://localhost/

# Should return a response for a PUT; send a real reading body from data/put_log.jsonl
curl -k -i -X PUT https://localhost/ -H 'Content-Type: application/json' -d '{}'
```

**6. Check the results and clean up**

```sh
ls -l ../data
docker compose logs --tail 50
docker compose down
```

The `../data` folder should contain the PUT log if `PUT_LOG` is `on`. 

**7. How to shut it down**

```sh
docker compose down
```
