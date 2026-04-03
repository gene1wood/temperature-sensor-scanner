# temperature-sensor-scanner

A tool to scan nearby Bluetooth Low Energy thermometers on the Telink chipset, collect the data ane emit it into
InfluxDB.

## Setup

* Create an influxdb user with a command like `influx user create --org [my-org] --name [my-username] --password [my-password]`
* Create an influxdb token with a command like `influx auth create --org [my-org] --user [my-username] --write-bucket [my-bucket-id]`
* Ensure the host supports at least Bluetooth 4.0 which is when BLE was first introduced
* Ensure bluetooth is working
  * `rfkill list` should show that `Soft blocked` and `Hard blocked` are both `no`, if not `rfkill unblock bluetooth && rfkill list && systemctl restart bluetooth`
* Create a `config.yaml` in `~/.config/temperature-sensor-scanner/` based on the `config.example.yaml` file
* Install this tool with a command like `pip install temperature-sensor-scanner`

## Usage

Run `temperature-sensor-scanner` which will scan for nearby sensors which are emitting temperature data in their Bluetooth
advertising string, collect that data, and emit it into InfluxDB.

## Setting up a service

Run this as the user you want to run the service

```shell
mkdir -p ~/.config/systemd/user/
cp temperature-sensor-scanner.service ~/.config/systemd/user/
cp temperature-sensor-scanner.timer ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now temperature-sensor-scanner.timer

sudo loginctl enable-linger $USER

systemctl --user list-timers
systemctl --user status temperature-sensor-scanner.service
journalctl --user -u temperature-sensor-scanner.service
```

# Notes

* https://github.com/pvvx/ATC_MiThermometer/
* https://pvvx.github.io/ATC_MiThermometer/TelinkMiFlasher.html
  * Launch in Chrome instead of Firefox
* Other tools that look interesting
  * https://github.com/JsBergbau/MiTemperature2

## Steps to provision a new sensor

* [Flash the firmware](https://github.com/pvvx/ATC_MiThermometer/?tab=readme-ov-file#flashing-or-updating-the-firmware-ota)
  * Click `Connect`
  * Select the `LYWSD03MMC` Bluetooth device in the menu
  * Click `Do Activation`
  * Choose `Custom Firmware ATC_v56.bin`
  * Click `Start Flashing`
  * Wait 42 seconds for it to show update done
* Identify ID from Bluetooth announced name and print a label to put on the sensor
* Quit Chrome and start again
* [Configure sensor](https://github.com/pvvx/ATC_MiThermometer/?tab=readme-ov-file#configuration)
  * Set display to Farenheight
  * Click `Set Time`
  * Set advertising type to `ATC1441`
  * Set advertising interval to `10000` ( https://github.com/pvvx/ATC_MiThermometer/issues/23#issuecomment-766898945 )
  * Set Measure interval: to 10
  * Click `Send Config`
