# AvNav Meshtastic Plugin

An [AvNav](https://github.com/wellenvogel/avnav) plugin that allows you to monitor your boat using [Meshtastic](https://meshtastic.org) radios. Meshtastic is based on LoRa long distance radio transmission that can easily cover a few kilometers. 
It periodically broadcasts GPS position and environmental telemetry (wind speed and direction, pressure, anchor distance) over the Meshtastic mesh network, and forwards active AvNav alarms as text messages.

This can be used e.g. to receive an alert when your anchor drags, even when you are not on the boat and don't have a mobile phone connection.

## Features

- **GPS position packets** — broadcasts latitude, longitude, SOG, HDOP, satellite count and fix quality as native Meshtastic `POSITION_APP` protobuf packets, showing up as node position in the Meshtastic app on the map and position log
- **Environmental telemetry** — sends true wind speed/direction, gusts, barometric pressure, temperature, humidity and anchor watch distance as `TELEMETRY_APP / EnvironmentMetrics` packets, diplayed as environment data in the Meshtastic app
- **Power telemetry** — sends battery voltage and current for up to two channels (house bank, starter battery, etc.) as `TELEMETRY_APP / PowerMetrics` packets; each channel is independently configurable via an AvNav data key
- **Alarm forwarding** — detects active AvNav alarms and sends them as text messages over the mesh; repeats at a configurable interval until cleared
- **Remote alarm control** — accepts `alarm silent`, `alarm active` and `alarm status` commands received over the mesh

## Hardware

- Raspberry Pi (or another computer) running AvNav
- A Meshtastic-compatible device connected via USB serial to your AvNav computer
- Another Meshtastic device that you carry with you connected via bluetooth to your phone. If possilbe this should have a buzzer or vibration unit for alarms. 

Popular devices include the Heltec V3/V4 and the SenseCap T1000-E, the latter being IP65-rated and ideal for carrying with you.

## Preparing the Meshtastic devices

- You need to install Meshtastic on both devices. Follow the instructions on the [Meshtastic](https://meshtastic.org) website. 
- Install Meshtastic app on your phone.
- Connect the device that shall connect via USB to your Raspberry via Bluetooth to your phone for configuration with the Meshtastic app
- configure the device
    - channel 0 is public. If you transmit here, everybody in your neighborhoud can read it and also see your position. They can also message to your device. 
    - Therefore you should configure a private encrypted channel, that only your devices join. You should also enable full position precision here in the channel settings.
    - In the AvNav plugin configuration, you can select this channel number for communication later.
- Disconnect the first device from your phones meshtastic app, connect the second one and repeat the configuration. Both devices must join the same private channel.
    - If the device you connect to your phone has a buzzer, go to Settings -> Module Configuration -> External Notifications and turn on alert when receiving a bell. Alarm messages are sent with a bell character. 

## Installation

### Option A — .deb package (recommended)

Download the `.deb` for your architecture (`arm64`, `armhf`, or `amd64`) from the [Releases](../../releases) page, then install it:

```bash
sudo apt install ./avnav-meshtastic-plugin_<version>_<arch>.deb
```

### Option B — zip archive

1. Download the source zip from the [Releases](../../releases) page and extract it.
2. In the extracted folder, install the required Python libraries into the plugin's `lib/` directory:
   ```bash
   ./install_non_deb_dependencies.sh
   ```
3. Copy the plugin into AvNav's user plugin directory:
   ```bash
   cp -r meshtastic ~/avnav/data/plugins/meshtastic
   ```

### Restart AvNav

```bash
sudo systemctl restart avnav
```

The plugin appears on the AvNav status page once it starts.

## Configuration

Plug in your Meshtastic device to a free USB port.

All settings are editable from the AvNav status page under the plugin entry.
You need to configure the USB port ID to which your device is connected. You can find it by looking at AvNavs USBSerialReader status. It will show a device and try to connect to it but cannot (because its a Meshtastic device). Enter this usbid into the plugin config and restart AvNav. Now the USBSerialReader will ignore this USB port and the plugin can connect to it.

Also remember to change the channel to your private channel number!

| Parameter | Default | Description |
|---|---|---|
| `usbid` | `1-2:1.0` | AvNav USB port ID — prevents AvNav treating the device as a NMEA source |
| `channel` | `0` | Meshtastic channel index for outgoing messages. Change this to a private channel! |
| `pos_interval` | `60` | Seconds between GPS position broadcasts (0 to disable) |
| `alarm_interval` | `60` | Seconds between repeated sends of each active alarm (0 to disable) |
| `env_interval` | `120` | Seconds between environment telemetry sends (0 to disable) |
| `pressure_key` | `gps.signalk.environment.outside.pressure` | AvNav key for barometric pressure (Pa, Signal K). Leave empty to disable pressure transmission |
| `temperature_key` | *(empty)* | AvNav key for outside air temperature (°C). Leave empty to disable |
| `humidity_key` | *(empty)* | AvNav key for relative humidity (%). Leave empty to disable |
| `power_interval` | `300` | Seconds between power telemetry sends (CH1/CH2); 0 to disable |
| `ch1_voltage_key` | *(empty)* | AvNav key for CH1 battery voltage (V). Leave empty to disable CH1 |
| `ch1_current_key` | *(empty)* | AvNav key for CH1 current (**A**). Leave empty to disable. The plugin converts A → mA before transmitting |
| `ch2_voltage_key` | *(empty)* | AvNav key for CH2 battery voltage (V). Leave empty to disable CH2 |
| `ch2_current_key` | *(empty)* | AvNav key for CH2 current (**A**). Leave empty to disable. The plugin converts A → mA before transmitting |
| `test_mode` | `false` | Use hardcoded test values instead of live AvNav data; also sends a debug counter message every 60 s |

## Remote Commands

Send any of these as a plain text message on the configured channel to control the plugin remotely:

| Command | Effect |
|---|---|
| `alarm silent` | Pause alarm forwarding |
| `alarm active` | Resume alarm forwarding |
| `alarm status` | Reply with current alarm forwarding state |
| `help` | Reply with list of commands |

## Meshtastic transmitted values to AvNav key mapping

### Position packet (`POSITION_APP`)

| AvNav key | Meshtastic field |
|---|---|
| `gps.lat` | `Position.latitude_i` |
| `gps.lon` | `Position.longitude_i` |
| `gps.speed` | `Position.ground_speed` |
| `gps.headingTrue` / `gps.sail_instrument.HDT` | `Position.ground_track` |
| `gps.signalk.navigation.gnss.horizontalDilution` | `Position.HDOP` |
| `gps.satUsed` | `Position.sats_in_view` |
| *(derived from lat/lon presence)* | `Position.fix_quality` |

### Environment telemetry packet (`TELEMETRY_APP / EnvironmentMetrics`)

| AvNav key | Meshtastic field |
|---|---|
| `gps.trueWindSpeed` / `gps.sail_instrument.TWS` | `EnvironmentMetrics.wind_speed` |
| `gps.trueWindDirection` / `gps.sail_instrument.TWD` | `EnvironmentMetrics.wind_direction` |
| `gps.sail_instrument.TWSMAX` | `EnvironmentMetrics.wind_gust` |
| `pressure_key` (configurable, default `gps.signalk.environment.outside.pressure`) | `EnvironmentMetrics.barometric_pressure` |
| `temperature_key` (configurable, empty = disabled) | `EnvironmentMetrics.temperature` |
| `humidity_key` (configurable, empty = disabled) | `EnvironmentMetrics.relative_humidity` |
| *(AVNRouter anchor watch leg, in-process)* | `EnvironmentMetrics.distance` |

### Power telemetry packet (`TELEMETRY_APP / PowerMetrics`)

Each field is only transmitted when its corresponding AvNav key is configured and the key has a value.
Current values are expected in **amperes (A)** — the plugin multiplies by 1000 before transmitting to match the protobuf convention of milliamperes (mA).

| Config parameter | Meshtastic field | Unit |
|---|---|---|
| `ch1_voltage_key` | `PowerMetrics.ch1_voltage` | V |
| `ch1_current_key` | `PowerMetrics.ch1_current` | A (transmitted as mA) |
| `ch2_voltage_key` | `PowerMetrics.ch2_voltage` | V |
| `ch2_current_key` | `PowerMetrics.ch2_current` | A (transmitted as mA) |

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE.md).

It depends on the [meshtastic](https://github.com/meshtastic/python) Python library (GPL-3.0) and runs inside [AvNav](https://github.com/wellenvogel/avnav) (MIT).
