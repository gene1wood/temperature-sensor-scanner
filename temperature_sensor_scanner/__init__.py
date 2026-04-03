#!/usr/bin/env python3

import asyncio
from bleak import BleakScanner  # pip install bleak
from bleak.exc import BleakDBusError
from functools import partial
from atc_mi_interface import (
    general_format,
    atc_mi_advertising_format,
)  # pip install atc-mi-interface

# atc-mi-interface
# https://github.com/pvvx/ATC_MiThermometer/tree/master/python-interface#decoding-and-encoding
import influxdb_client  # pip install influxdb-client
from influxdb_client.client.write_api import SYNCHRONOUS

import sys
from pathlib import Path

import yaml  # pip install PyYAML
from platformdirs import user_config_dir  # pip install platformdirs

APP_NAME = "temperature-sensor-scanner"
APP_AUTHOR = "Cementhorizon"


def get_config_path() -> Path:
    """
    Returns the full path to config.yaml in the user config directory.
    Example:
      Linux:   ~/.config/APP_NAME/config.yaml
      macOS:   ~/Library/Application Support/APP_NAME/config.yaml
      Windows: C:\\Users\\<user>\\AppData\\Local\\APP_AUTHOR\\APP_NAME\\config.yaml
    """
    config_dir = Path(user_config_dir(APP_NAME, APP_AUTHOR))
    return config_dir / "config.yaml"


def load_config(path: Path) -> dict:
    """
    Loads YAML config.
    """
    if not path.exists():
        print("Missing parsing config file", file=sys.stderr)
        sys.exit(1)

    try:
        with path.open("r") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"Error parsing config file: {e}", file=sys.stderr)
        sys.exit(1)


def gather_data(config: dict) -> list:
    scan_results = asyncio.run(ble_coro(config))

    # name = atc_mi_data.atc1441_format[0].MAC.replace(":", "")[-6:]
    # print(f"ATC_{name} : {temperature:.1f}")

    points = []
    macs_seen = set()
    for scan_result in scan_results:
        if scan_result["mac"] in macs_seen:
            continue
        else:
            macs_seen.add(scan_result["mac"])
        sensor = config["sensors"][scan_result["mac"]]
        points.append(
            influxdb_client.Point("environment")
            .tag("location", sensor["location"])
            .tag("domain", sensor["domain"])
            .tag("mac", scan_result["mac"])
            .field("temperature", scan_result["temperature"])
        )
    return points


def emit_data(config: dict, points: list) -> None:
    bucket = config["influxdb"]["bucket"]
    org = config["influxdb"]["org"]
    token = config["influxdb"]["token"]
    url = config["influxdb"]["url"]

    client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)

    write_api = client.write_api(write_options=SYNCHRONOUS)
    write_api.write(bucket=bucket, org=org, record=points)


async def ble_coro(config):
    timeout = config.get("scan_timeout_seconds", 30)  # default 30s
    stop_event = asyncio.Event()
    results = []
    seen_macs = set()

    def detection_callback(device, advertisement_data):
        format_label, adv_data = atc_mi_advertising_format(advertisement_data)
        if not adv_data:
            return
        device_address = device.address.replace(":", "")
        if device_address not in config["sensors"]:
            print(f"Detected unknown device: {device_address}")
            return

        mac_address = bytes.fromhex(device_address)
        bindkey = config["sensors"][device_address.replace(":", "")]["bindkey"]

        atc_mi_data = general_format.parse(
            adv_data,
            mac_address=mac_address,
            bindkey=None if bindkey is None else bytes.fromhex(bindkey),
        )
        mac = atc_mi_data.atc1441_format[0].MAC.replace(":", "")
        name = mac[-6:]

        if atc_mi_data.atc1441_format[0].temperature_unit == "°C":
            temperature = (atc_mi_data.atc1441_format[0].temperature * 1.8) + 32
        else:
            temperature = atc_mi_data.atc1441_format[0].temperature

        print(f"ATC_{name} : {temperature:.1f}")
        results.append({"mac": mac, "temperature": temperature})

        # Stop early once we've heard from every configured sensor
        seen_macs.add(mac)
        if seen_macs >= set(config["sensors"].keys()):
            stop_event.set()

    try:
        async with BleakScanner(detection_callback=detection_callback) as scanner:
            # Use shield + wait instead of wait_for, so the timeout does NOT
            # cancel the task — we just stop waiting and let the context manager
            # exit cleanly on its own.
            done, pending = await asyncio.wait(
                [asyncio.get_event_loop().create_task(stop_event.wait())],
                timeout=timeout,
            )
            if not done:
                print(f"Scan timed out after {timeout}s — returning {len(results)} result(s)")
            # Exiting the `async with` block here always runs scanner cleanup
            # synchronously and correctly, regardless of whether we timed out.
    except BleakDBusError as e:
        # On Linux/BlueZ, stopping a scan that found no devices can raise
        # "Operation already in progress" due to a race condition in BlueZ
        if "InProgress" not in str(e):
            raise

    return results


def main():
    config_path = get_config_path()
    config = load_config(config_path)
    points = gather_data(config)
    emit_data(config, points)


if __name__ == "__main__":
    main()
