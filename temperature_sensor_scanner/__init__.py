#!/usr/bin/env python3

import asyncio
from bleak import BleakScanner  # pip install bleak
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
    count = [0]
    stop_event = asyncio.Event()
    results = []

    def detection_callback(count, results, device, advertisement_data):
        format_label, adv_data = atc_mi_advertising_format(advertisement_data)
        if not adv_data:
            return
        mac_address = bytes.fromhex(device.address.replace(":", ""))
        bindkey = config["sensors"][device.address.replace(":", "")]["bindkey"]

        atc_mi_data = general_format.parse(
            adv_data,
            mac_address=mac_address,
            bindkey=None if bindkey is None else bytes.fromhex(bindkey),
        )
        name = atc_mi_data.atc1441_format[0].MAC.replace(":", "")[-6:]
        if atc_mi_data.atc1441_format[0].temperature_unit == "°C":
            temperature = (atc_mi_data.atc1441_format[0].temperature * 1.8) + 32
        else:
            temperature = atc_mi_data.atc1441_format[0].temperature
        print(f"ATC_{name} : {temperature:.1f}")

        results.append({
            "mac": atc_mi_data.atc1441_format[0].MAC.replace(":", ""),
            "temperature": temperature,
        })

        count[0] += 1
        if count[0] == 8:
            stop_event.set()

    async with BleakScanner(
        detection_callback=partial(detection_callback, count, results)
    ) as scanner:
        await stop_event.wait()
    return results


def main():
    config_path = get_config_path()
    config = load_config(config_path)
    points = gather_data(config)
    emit_data(config, points)


if __name__ == "__main__":
    main()
