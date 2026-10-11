#!/usr/bin/env python3
"""Configure an EcoQube's Wi-Fi over BLE.

Vibecoded by Github Copilot (2026)
Copyright (c) 2026 EpicRE

Commands:
  scan   list nearby EcoQube devices
  info   show device information
  setup  pick a device, pick a Wi-Fi network, send credentials
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

SERVICE_UUID = "00001523-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "00001524-0000-1000-8000-00805f9b34fb"   # app -> device
NOTIFY_UUID = "00001525-0000-1000-8000-00805f9b34fb"  # device -> app

CMD_DISCONNECT = 0xA0
CMD_DEVICE_INFO = 0xB0
CMD_WIFI_SCAN = 0xB1
CMD_WIFI_SET = 0xB2

SCAN_SECONDS = 5.0
ACK_TIMEOUT = 15.0
WIFI_SET_TIMEOUT = 90.0


class IncompleteFrame(Exception):
    """Raised by parsers when more notification bytes are needed."""


def checksum(data: bytes) -> int:
    return 255 - (sum(data) & 0xFF)


def frame(cmd: int, payload: bytes = b"") -> bytes:
    body = bytes([cmd]) + payload
    return body + bytes([checksum(body)])


def serial_text(name: str) -> str:
    parts = name.split(":")
    return parts[2] if len(parts) >= 3 else name


def is_ecoqube(name: str) -> bool:
    # Name contains "FR", serial is EQ-prefixed at index 4, EP/ES/EQQG excluded.
    if not name or "FR" not in name:
        return False
    text = serial_text(name)
    if text.find("EP") == 4:
        return False
    return text.find("EQ") == 4 and text.find("EQQG") != 4


@dataclass
class DeviceInfo:
    serial: str
    wifi_connected: bool
    firmware: str
    wifi_ssid: str
    api_url_main: str
    api_url_sub: str


@dataclass
class WifiNetwork:
    index: int
    vpn: int
    secret: bool
    rssi: int
    bssid: bytes
    ssid_raw: bytes

    @property
    def ssid(self) -> str:
        return self.ssid_raw.decode("utf-8", "replace")


def _need(data: bytes, end: int) -> None:
    if len(data) < end:
        raise IncompleteFrame


def _length_prefixed(data: bytes, pos: int) -> tuple[bytes, int]:
    _need(data, pos + 1)
    end = pos + 1 + data[pos]
    _need(data, end)
    return data[pos + 1:end], end


def parse_device_info(data: bytes) -> DeviceInfo:
    _need(data, 39)
    serial = data[1:13].decode("ascii", "replace")
    wifi_connected = data[16] == 1
    firmware, pos = _length_prefixed(data, 38)
    ssid, pos = _length_prefixed(data, pos)
    _, pos = _length_prefixed(data, pos)  # Wi-Fi password, not exposed
    api_main, pos = _length_prefixed(data, pos)
    api_sub, _ = _length_prefixed(data, pos)
    return DeviceInfo(
        serial=serial,
        wifi_connected=wifi_connected,
        firmware=firmware.decode("utf-8", "replace"),
        wifi_ssid=ssid.decode("utf-8", "replace"),
        api_url_main=api_main.decode("utf-8", "replace"),
        api_url_sub=api_sub.decode("utf-8", "replace"),
    )


def parse_wifi_scan(data: bytes) -> list[WifiNetwork]:
    _need(data, 2)
    count = data[1]
    networks: list[WifiNetwork] = []
    seen: set[bytes] = set()
    pos = 2
    for _ in range(count):
        _need(data, pos + 11)
        ssid_len = data[pos + 10]
        _need(data, pos + 11 + ssid_len)
        net = WifiNetwork(
            index=data[pos],
            vpn=data[pos + 1],
            secret=data[pos + 2] != 0,
            rssi=data[pos + 3] - 256,
            bssid=bytes(data[pos + 4:pos + 10]),
            ssid_raw=bytes(data[pos + 11:pos + 11 + ssid_len]),
        )
        pos += 11 + ssid_len
        if net.ssid_raw not in seen:
            seen.add(net.ssid_raw)
            networks.append(net)
    return networks


def wifi_set_frame(net: WifiNetwork, password: bytes) -> bytes:
    payload = (
        net.bssid
        + bytes([len(net.ssid_raw)]) + net.ssid_raw
        + bytes([len(password)]) + password
    )
    return frame(CMD_WIFI_SET, payload)


class EcoQubeLink:
    def __init__(self, client: BleakClient) -> None:
        self.client = client
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()

    def _on_notify(self, _sender, data: bytearray) -> None:
        self._queue.put_nowait(bytes(data))

    async def start(self) -> None:
        await self.client.start_notify(NOTIFY_UUID, self._on_notify)

    async def stop(self) -> None:
        await self.client.stop_notify(NOTIFY_UUID)

    async def write(self, data: bytes) -> None:
        size = max(20, self.client.mtu_size - 3)
        for i in range(0, len(data), size):
            await self.client.write_gatt_char(WRITE_UUID, data[i:i + size], response=False)
            await asyncio.sleep(0.05)

    async def request(self, data: bytes, expect_cmd: int, parser, timeout: float):
        while not self._queue.empty():
            self._queue.get_nowait()
        await self.write(data)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        buf = bytearray()
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"no response for command 0x{expect_cmd:02X}")
            chunk = await asyncio.wait_for(self._queue.get(), remaining)
            if not buf and (not chunk or chunk[0] != expect_cmd):
                continue
            buf += chunk
            try:
                return parser(bytes(buf))
            except IncompleteFrame:
                continue


async def discover(seconds: float) -> list[BLEDevice]:
    found = await BleakScanner.discover(timeout=seconds, return_adv=True)
    devices = []
    for device, adv in found.values():
        name = adv.local_name or device.name or ""
        if is_ecoqube(name):
            devices.append(device)
    return devices


async def with_link(device: BLEDevice, action):
    async with BleakClient(device, timeout=20.0) as client:
        link = EcoQubeLink(client)
        await link.start()
        try:
            return await action(link)
        finally:
            await link.stop()


async def read_info(link: EcoQubeLink) -> DeviceInfo:
    return await link.request(frame(CMD_DEVICE_INFO), CMD_DEVICE_INFO, parse_device_info, ACK_TIMEOUT)


async def read_networks(link: EcoQubeLink) -> list[WifiNetwork]:
    return await link.request(frame(CMD_WIFI_SCAN), CMD_WIFI_SCAN, parse_wifi_scan, ACK_TIMEOUT)


async def send_wifi(link: EcoQubeLink, net: WifiNetwork, password: bytes) -> DeviceInfo:
    info = await link.request(
        wifi_set_frame(net, password), CMD_DEVICE_INFO, parse_device_info, WIFI_SET_TIMEOUT
    )
    await link.write(frame(CMD_DISCONNECT))
    return info


def pick(items: list, label) -> int:
    for i, item in enumerate(items, 1):
        print(f"  {i}. {label(item)}")
    while True:
        choice = input("Select number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(items):
            return int(choice) - 1
        print("Invalid choice.")


async def cmd_scan(args) -> int:
    devices = await discover(args.seconds)
    if not devices:
        print("No EcoQube devices found.")
        return 1
    for d in devices:
        print(f"{d.name or '(no name)'}  {d.address}")
    return 0


async def cmd_info(args) -> int:
    device = await select_device(args)
    if device is None:
        return 1
    info = await with_link(device, read_info)
    print(f"Serial:         {info.serial}")
    print(f"Firmware:       {info.firmware}")
    print(f"Wi-Fi SSID:     {info.wifi_ssid}")
    print(f"Wi-Fi connected: {info.wifi_connected}")
    print(f"API URL main:   {info.api_url_main}")
    print(f"API URL sub:    {info.api_url_sub}")
    return 0


async def cmd_setup(args) -> int:
    device = await select_device(args)
    if device is None:
        return 1

    async def action(link: EcoQubeLink):
        info = await read_info(link)
        print(f"Connected to {info.serial} (firmware {info.firmware}).")
        networks = await read_networks(link)
        if not networks:
            print("Device reported no Wi-Fi networks.")
            return None
        networks.sort(key=lambda n: n.rssi, reverse=True)
        print("Networks:")
        index = await asyncio.to_thread(
            pick, networks, lambda n: f"{n.ssid}  ({n.rssi} dBm{', secured' if n.secret else ', open'})"
        )
        net = networks[index]
        password = b""
        if net.secret:
            password = (await asyncio.to_thread(getpass.getpass, "Wi-Fi password: ")).encode("utf-8")
        print("Sending Wi-Fi settings...")
        result = await send_wifi(link, net, password)
        return result

    result = await with_link(device, action)
    if result is None:
        return 1
    if result.wifi_connected:
        print(f"Device connected to Wi-Fi '{result.wifi_ssid}'.")
        return 0
    print("Device reported Wi-Fi not connected. Check the password and try again.")
    return 2


async def select_device(args) -> BLEDevice | None:
    if args.address:
        devices = await discover(args.seconds)
        for d in devices:
            if d.address.lower() == args.address.lower():
                return d
        print(f"Device {args.address} not found.")
        return None
    devices = await discover(args.seconds)
    if not devices:
        print("No EcoQube devices found.")
        return None
    if len(devices) == 1:
        return devices[0]
    print("Devices:")
    return devices[pick(devices, lambda d: f"{d.name}  {d.address}")]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seconds", type=float, default=SCAN_SECONDS, help="scan duration")
    parser.add_argument("--address", help="device address/UUID to use (skips the device prompt)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="list nearby EcoQube devices")
    sub.add_parser("info", help="show device information")
    sub.add_parser("setup", help="configure Wi-Fi")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    handlers = {"scan": cmd_scan, "info": cmd_info, "setup": cmd_setup}
    try:
        return asyncio.run(handlers[args.command](args))
    except KeyboardInterrupt:
        return 130
    except (TimeoutError, asyncio.TimeoutError) as exc:
        print(f"Timed out: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
