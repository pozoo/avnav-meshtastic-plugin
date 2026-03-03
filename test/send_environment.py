#!/usr/bin/env python3
"""Send a Meshtastic environment telemetry packet from the command line.

Usage:
  python3 send_environment.py [wind_knots] [wind_dir_deg] [pressure_hpa] [wind_gust_knots] [channel]

Examples:
  python3 send_environment.py                           # defaults
  python3 send_environment.py 12.5 270 1013.2           # wind 12.5kt, from 270°, 1013.2 hPa
  python3 send_environment.py 12.5 270 1013.2 18.0      # same + gust 18kt
  python3 send_environment.py 12.5 270 1013.2 18.0 1   # same, channel 1

wind_speed is sent in m/s as required by the protobuf (converted from knots).
wind_direction is in degrees (0–359, 0=N).
barometric_pressure is in hPa.
"""

import sys
import time

sys.path.insert(0, '/home/pi/meshtastic/env/lib/python3.11/site-packages')

import meshtastic.serial_interface
from meshtastic.protobuf import telemetry_pb2, portnums_pb2

PORT = '/dev/ttyACM1'

KNOTS_TO_MS = 0.514444  # 1 knot = 0.514444 m/s

# Defaults
wind_knots = 10.0
wind_dir   = 180
pressure   = 1013.25
gust_knots = None
channel    = 0

if len(sys.argv) >= 2:
    wind_knots = float(sys.argv[1])
if len(sys.argv) >= 3:
    wind_dir = int(sys.argv[2])
if len(sys.argv) >= 4:
    pressure = float(sys.argv[3])
if len(sys.argv) >= 5:
    gust_knots = float(sys.argv[4])
if len(sys.argv) >= 6:
    channel = int(sys.argv[5])

wind_ms = wind_knots * KNOTS_TO_MS
gust_ms = gust_knots * KNOTS_TO_MS if gust_knots is not None else None

print(f"Connecting to {PORT} ...")
iface = meshtastic.serial_interface.SerialInterface(PORT)
time.sleep(1)

# Build Telemetry > EnvironmentMetrics protobuf
env = telemetry_pb2.EnvironmentMetrics()
env.wind_speed          = wind_ms
env.wind_direction      = wind_dir
env.barometric_pressure = pressure
if gust_ms is not None:
    env.wind_gust = gust_ms

telemetry = telemetry_pb2.Telemetry()
telemetry.environment_metrics.CopyFrom(env)

print(f"Sending environment telemetry:")
print(f"  wind_speed    = {wind_knots:.1f} kt  ({wind_ms:.2f} m/s)")
print(f"  wind_gust     = {f'{gust_knots:.1f} kt  ({gust_ms:.2f} m/s)' if gust_knots is not None else '(not set)'}")
print(f"  wind_direction= {wind_dir}°")
print(f"  pressure      = {pressure:.1f} hPa")
print(f"  channel       = {channel}")

iface.sendData(
    telemetry,
    portNum=portnums_pb2.PortNum.TELEMETRY_APP,
    channelIndex=channel,
)
time.sleep(2)

iface.close()
print("Done.")
