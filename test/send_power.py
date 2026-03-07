#!/usr/bin/env python3
"""Send a single Meshtastic PowerMetrics telemetry packet with yacht electrical data.

Uses the Telemetry > PowerMetrics protobuf (portnum TELEMETRY_APP = 67).
Up to 8 independent voltage + current channels are available.

Yacht channel mapping used here:
  Ch1  House battery bank (12 V nominal)   voltage + load current
  Ch2  Starter battery                     voltage + current
  Ch3  Solar panel input                   voltage + charging current
  Ch4  Wind generator input                voltage + charging current

Usage:
  python3 send_power.py [channel_index]

  channel_index  Meshtastic channel index to send on (default: 1)
"""

import sys
import time

sys.path.insert(0, '/home/pi/meshtastic/env/lib/python3.11/site-packages')

import meshtastic.serial_interface
from meshtastic.protobuf import telemetry_pb2, portnums_pb2

PORT    = '/dev/ttyACM0'
CHANNEL = 1

# ---------------------------------------------------------------------------
# Simulated yacht electrical readings
# ---------------------------------------------------------------------------
# Ch1 – House battery bank: 12.8 V, drawing 18.4 A (nav instruments + fridge)
CH1_V = 12.8
CH1_A = 18.4

# Ch2 – Starter battery: 12.6 V, 0.2 A (trickle from combiner)
CH2_V = 12.6
CH2_A =  0.2

# Ch3 – Solar panel: 17.3 V open-circuit, charging at 8.5 A
CH3_V = 17.3
CH3_A =  8.5

# Ch4 – Wind generator: 14.1 V, charging at 4.2 A (12 kn true wind)
CH4_V = 14.1
CH4_A =  4.2
# ---------------------------------------------------------------------------

print(f"Connecting to {PORT} ...")
iface = meshtastic.serial_interface.SerialInterface(PORT)
time.sleep(1)

# Build Telemetry > PowerMetrics
# Note: ch{n}_current is in mA (proto convention), so multiply A values by 1000
pm = telemetry_pb2.PowerMetrics()
pm.ch1_voltage = CH1_V
pm.ch1_current = CH1_A * 1000
pm.ch2_voltage = CH2_V
pm.ch2_current = CH2_A * 1000
pm.ch3_voltage = CH3_V
pm.ch3_current = CH3_A * 1000
pm.ch4_voltage = CH4_V
pm.ch4_current = CH4_A * 1000

t = telemetry_pb2.Telemetry()
t.time          = int(time.time())
t.power_metrics.CopyFrom(pm)

payload = t.SerializeToString()

iface.sendData(
    payload,
    portNum=portnums_pb2.PortNum.TELEMETRY_APP,
    channelIndex=CHANNEL,
)

print()
print("PowerMetrics packet sent")
print(f"  Ch1  House battery   {CH1_V:.1f} V  {CH1_A:+.1f} A  "
      f"({CH1_V * CH1_A:.0f} W load)")
print(f"  Ch2  Starter battery {CH2_V:.1f} V  {CH2_A:+.1f} A")
print(f"  Ch3  Solar panel     {CH3_V:.1f} V  {CH3_A:+.1f} A  "
      f"({CH3_V * CH3_A:.0f} W in)")
print(f"  Ch4  Wind generator  {CH4_V:.1f} V  {CH4_A:+.1f} A  "
      f"({CH4_V * CH4_A:.0f} W in)")

net_w = (CH3_V * CH3_A + CH4_V * CH4_A) - (CH1_V * CH1_A)
print(f"  Net balance          {net_w:+.0f} W  "
      f"({'charging' if net_w > 0 else 'discharging'})")

iface.close()
