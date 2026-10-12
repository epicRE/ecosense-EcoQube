# EcoQube 
Self-hosted local-only EcoQube by Ecosense

## ! WARNING !
**This is an experimental system, use at your own risk. I can't be held liable for any and all issues you might face afterward using this code. I can't be held liable for any damage to the hardware or your computer system due to coding issues in the programs and scripts provided.**

## Introduction
This repo is about the EcoQube from Ecosense ([https://ecosense.io/products/ecoqube](https://ecosense.io/products/ecoqube)). 

Inspired by https://github.com/starsoccer/ecosense/ the process below will remove Ecosense mobile application and the backend.

I provide all the information needed for you to setup and run the EcoQube without any account or connection to the Ecosense backend.

I detail how to a) setup your EcoQube out of the box (no mobile application needed) and b) how to setup a local web server that will accept the HTTP requests made by the device and send formatted MQTT messages that are compatible with Home Assistant (auto-discovery in MQTT).

You will need (pre-requisites): 

Part 1:
* A EcoQube Device
* Bluetooth enabled device for the setup script ([ecoqube_ble.py](ecoqube_ble.py))

Part 2:
* The same EcoQube Device from part 1
* Docker (or just run the [ecoqube-web2mqtt-server.py](ecoqube-web2mqtt-server.py))
* A system (Linux) listening on 443 (or use a redirect service like nginx etc) 
* DNS Rewriting service (i.e., AdGuard, local DNS etc) for 'api.cloud.ecosense.io'
* Home Assistant with a MQTT server
  
# How to connect and setup the device (step one)

```bash
python3 -m pip install --upgrade pip
python3 -m venv .venv
source .venv/bin/activate
git clone https://github.com/epicRE/ecosense-EcoQube/
cd ecosense-EcoQube
pip3 install -r requirements.txt
python3 ecoqube_ble.py
```

```bash
usage: ecoqube_ble.py [-h] [--seconds SECONDS] [--address ADDRESS] {scan,info,setup} ...
ecoqube_ble.py: error: the following arguments are required: command
```

Let's scan for device(s):
```bash
python3 ecoqube_ble.py scan
```

You will be presented with a list of devices (depends on what is in range):
```bash
FR:EQ:JF10EQ00XXXX  5410156B-7BF5-E489-5288-0769BB6196A9
```

For the next commands I recommend you make use of the serial flag (`--serial JF10EQ00XXXX`) to correctly target the device you want. 
```bash
python3 ecoqube_ble.py --serial JF10EQ00XXXX info
```

You should get this output if you have you have not configure it: 

```bash
Serial:         JF10EQ00XXXX
Firmware:       X.XX.X
Wi-Fi SSID:     FTLAB_RESEARCH
Wi-Fi connected: False
API URL main:   https://api.cloud.ecosense.io
API URL sub:    /api/v1/radon
```

Setup the wifi now. You will get a list of wifi said (pick the number) and then provide the password.

```bash
python3 ecoqube_ble.py --serial JF10EQ00XXXX setup
```

If successful you should get the following. It will then throw an error and disconnect (this is correct). 
```bash
Connected to JF10EQ00XXXX (firmware X.XX.X).
Networks:
  1. SSID1  (-XX dBm, secured)
  2. SSID2  (-XX dBm, secured)

Select number: 1
Wi-Fi password: 
Sending Wi-Fi settings...
Error: disconnected
```

Run info again to check that it is connected
```bash
python3 ecoqube_ble.py --serial JF10EQ00XXXX info
```

Correct setup: 
```bash
Serial:         JF10EQ00XXXX
Firmware:       X.XX.X
Wi-Fi SSID:     SSID1
Wi-Fi connected: True
API URL main:   https://api.cloud.ecosense.io
API URL sub:    /api/v1/radon
```

# Setup a local web server (with TLS) that will accept and send the readings to an MQTT server (step two)

Check the docker [docker/README.md](docker/README.md)

# Extra information (the details)

## BLE (bluetooth)
The device is unlocked and anyone can connect via BLE (bluetooth) and query or setup the device. 

## Webserver PUT requests
The device makes webserver PUT requests to the domain 'api.cloud.ecosense.io' over a TLS connection without any verification.

## JSON format (sensitive information replaced with X) 

This is the body of the JSON 
```json
{
    "serial_number": "JF10EQ00XXXX",
    "d_type": 0,
    "p_time": 0,
    "d_status": 0,
    "radon_level": 0,
    "radon_dou": 0,
    "d_debug": {
        "FW_MODE": 0,
        "PUT_CNT": 4,
        "PUT_ERR": 0,
        "PUT_STS": 2,
        "PUT_T": 10,
        "D_RE": 1,
        "F_RE": 0,
        "OTA_CHK": "0000",
        "W_RECONN": 0,
        "IP_L_CNT": 0,
        "SEND_S_TS": 180157,
        "SEND_E_TS": 182403,
        "ERR_7004_LEN": 114,
        "ERR_7004_1": 0,
        "ERR_7004_2": 0,
        "ERRORS": [
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 320753
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 331814
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 11063
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 21833
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 32793
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 69664
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 80823
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 91773
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 129673
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 140823
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 151783
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 20113
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 31213
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 42273
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 69713
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 80773
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 91833
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 120235
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 121765
            },
            {
                "cmd": "0000",
                "sts": 0,
                "ts": 123311
            }
        ]
    },
    "c_factor": 1.17,
    "fw_version": "X.XX.X"
}
```

## Test PUT request 
(send to [ecoqube-web2mqtt-server.py](ecoqube-web2mqtt-server.py))

```bash
curl -sk --retry 10 --retry-connrefused -o /dev/null -w "%{http_code}\n" -X PUT -H "Content-Type: application/json" --data '{"serial_number":"JF10EQ001001","d_type":0,"p_time":0,"d_status":0,"radon_level":0,"radon_dou":0,"c_factor":1.17,"fw_version":"1.1.X"}' https://127.0.0.1:8443/api/v1/radon;
```

# Attribution
https://github.com/epicRE/ecosense-EcoQube/ by EpicRE (2026)

Many thanks to https://github.com/starsoccer/ecosense/ for the insights about the MQTT format.
