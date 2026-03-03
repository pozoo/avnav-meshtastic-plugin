# AVnav Meshtastic Plugin

An [AvNav](https://github.com/wellenvogel/avnav) plugin that allows you to monitor your boat using [Meshtastic](https://meshtastic.org) radios. Meshtastic is based on Lora long distance radio transmission that can easily cover few kilometers. 
It periodically broadcasts GPS position and environmental telemetry (wind speed and direction, pressure, anchor distance) over the Meshtastic mesh network, and forwards active AVnav alarms as text messages.

This can be used e.g. to receive an alert when your anchor drags, even when you are not on the boat and don't have a mobile phone connection.

## Features

- **GPS position packets** — broadcasts latitude, longitude, SOG, HDOP, satellite count and fix quality as native Meshtastic `POSITION_APP` protobuf packets
- **Environmental telemetry** — sends true wind speed/direction, gusts, barometric pressure and anchor watch distance as `TELEMETRY_APP / EnvironmentMetrics` packets
- **Alarm forwarding** — detects active AVnav alarms and sends them as text messages over the mesh; repeats at a configurable interval until cleared
- **Remote alarm control** — accepts `alarm silent`, `alarm active` and `alarm status` commands received over the mesh


## Requirements

### Hardware

- Raspberry Pi (or another computer) running AvNav
- A Meshtastic-compatible device connected via USB serial
- Another Meshtastic device that you carry with you connected via bluetooth to your phone. If possilbe this should have a buzzer or vibration unit for alarms.

### Preparing the Meshtastic devices

- You need to install Meshtastic on both devices. Follow the instructions on the [Meshtastic](https://meshtastic.org) website. 
- Install meshtastic software on your phone.
- Connect the device that shall connect via USB to your Raspberry via Bluetooth to your phone for configuration with the Meshtastic app
- configure the device
    - channel 0 is public. If you transmit here, everybody in your neighborhoud can read it and also see your position. They can also message to your device. 
    - Therefore you should configure a private encrypted channel, that only your devices join. You should also enable full position precision here in the channel settings.
    - In the AvNav plugin configuration, you can select this channel number for communication later.
- Disconnect the first device from your phones meshtastic app, connect the second one and repeat the configuration. Both devices must join the same private channel.
    - If the device you connect to your phone has a buzzer, go to Settings -> Module Configuration -> External Notifications and turn on alert when receiving a bell. Alarm messages are sent with a bell character. 

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/avnav-meshtastic.git
cd avnav-meshtastic
```

### 3. Install the meshtastic Python library into the plugin meshtastic/lib folder

```bash
./install_non_deb_dependencies.sh
```

This runs `pip3 install -t meshtastic/lib -r requirements.txt` and places the library files directly into `meshtastic/lib/`. It does not install files elsewhere on your computer.

### 4. Install the plugin into AVnav

Copy (or symlink) the `meshtastic/` folder into AVnav's plugin directory:

```bash
ln -s "$(pwd)/meshtastic" ~/.avnav/plugins/meshtastic
```

Or copy it:

```bash
cp -r meshtastic ~/.avnav/plugins/meshtastic
```

### 5. Restart AVnav

```bash
sudo systemctl restart avnav
```

The plugin should appear on the AVnav status page. If the Meshtastic device is connected it will show status `NMEA` (AVnav's "connected" state).

## Configuration

All settings are editable from the AVnav status page under the plugin entry.
You need to configure the USB port ID to which your device is connected. You can find it by looking at AvNavs USBSerialReader Status. It will show a device and try to connect to it but cannot (because its a Meshtastic device). Enter this usbid into the plugin config and restart AvNav. Now it will ignore this USB port and the plugin can connect to it.

Also remember to change the channel to your private channel number!

| Parameter | Default | Description |
|---|---|---|
| `usbid` | `1-2:1.0` | AVnav USB port ID — prevents AVnav treating the device as a NMEA source |
| `channel` | `0` | Meshtastic channel index for outgoing messages |
| `pos_interval` | `60` | Seconds between GPS position broadcasts (0 to disable) |
| `alarm_interval` | `60` | Seconds between repeated sends of each active alarm (0 to disable) |
| `env_interval` | `120` | Seconds between environment telemetry sends (0 to disable) |
| `debug_interval` | `0` | Minutes between debug counter messages (0 to disable) |
| `test_mode` | `false` | Use hardcoded test values instead of live AVnav data |

## Remote Commands

Send any of these as a plain text message on the configured channel to control the plugin remotely:

| Command | Effect |
|---|---|
| `alarm silent` | Pause alarm forwarding |
| `alarm active` | Resume alarm forwarding |
| `alarm status` | Reply with current alarm forwarding state |
| `help` | Reply with list of commands |


## License

This project is licensed under the [GNU General Public License v3.0](LICENSE.md).

It depends on the [meshtastic](https://github.com/meshtastic/python) Python library (GPL-3.0) and runs inside [AVnav](https://github.com/wellenvogel/avnav) (MIT).
