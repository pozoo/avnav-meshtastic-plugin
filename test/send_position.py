#!/usr/bin/env python3
"""Send a Meshtastic position report from the command line.

Usage:
  python3 send_position.py lat lon sog_kt cog_deg hdop sats fix_quality [channel]

Arguments:
  lat          Latitude in decimal degrees
  lon          Longitude in decimal degrees
  sog_kt       Speed over ground in knots
  cog_deg      Course over ground in degrees true (0-359)
  hdop         Horizontal dilution of precision (e.g. 1.2)
  sats         Satellites in view
  fix_quality  GPS fix quality (0=invalid, 1=GPS, 2=DGPS)
  channel      Channel index (default: 0)

Examples:
  python3 send_position.py 51.081 12.545 6.5 270 1.2 8 1
  python3 send_position.py 51.081 12.545 6.5 270 1.2 8 1 0
"""

import sys
import time as _time

sys.path.insert(0, '/home/pi/meshtastic/env/lib/python3.11/site-packages')

import meshtastic.serial_interface
from meshtastic import mesh_pb2, portnums_pb2

KNOTS_TO_KMH = 1.852  # 1 knot = 1.852 km/h  (firmware uses km/h despite proto docs saying m/s)

PORT = '/dev/ttyACM0'

# Defaults
lat         = 50.08100
lon         = 10.54533
sog_kt      = 0.0
cog_deg     = 0
hdop        = 1.0
sats        = 0
fix_quality = 0
channel     = 0

if len(sys.argv) >= 3:
    lat     = float(sys.argv[1])
    lon     = float(sys.argv[2])
if len(sys.argv) >= 4:
    sog_kt  = float(sys.argv[3])
if len(sys.argv) >= 5:
    cog_deg = float(sys.argv[4])
if len(sys.argv) >= 6:
    hdop    = float(sys.argv[5])
if len(sys.argv) >= 7:
    sats    = int(sys.argv[6])
if len(sys.argv) >= 8:
    fix_quality = int(sys.argv[7])
if len(sys.argv) >= 9:
    channel = int(sys.argv[8])

sog_kmh = sog_kt * KNOTS_TO_KMH

print(f"Connecting to {PORT} ...")
iface = meshtastic.serial_interface.SerialInterface(PORT)
_time.sleep(1)

now = int(_time.time())

p = mesh_pb2.Position()
p.latitude_i   = int(lat * 1e7)
p.longitude_i  = int(lon * 1e7)
p.time         = now
p.ground_speed = int(round(sog_kmh))
p.ground_track = int(round(cog_deg * 100))
p.HDOP         = int(round(hdop * 100))
p.sats_in_view = sats
p.fix_quality  = fix_quality
p.seq_number   = now & 0xFFFF  # lower 16 bits of unix time

print(f"Sending position:")
print(f"  lat          = {lat:.5f}°")
print(f"  lon          = {lon:.5f}°")
print(f"  time         = {now}")
print(f"  seq_number   = {p.seq_number}")
print(f"  SOG          = {sog_kt:.1f} kt  ({p.ground_speed} km/h)")
print(f"  COG          = {cog_deg:.1f}°  ({p.ground_track} / 100 deg)")
print(f"  HDOP         = {hdop:.1f}  ({p.HDOP} / 100)")
print(f"  sats_in_view = {sats}")
print(f"  fix_quality  = {fix_quality}")
print(f"  channel      = {channel}")

iface.sendData(
    p,
    portNum=portnums_pb2.PortNum.POSITION_APP,
    channelIndex=channel,
)
_time.sleep(2)

iface.close()
print("Done.")
