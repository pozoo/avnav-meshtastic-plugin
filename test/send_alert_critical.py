#!/usr/bin/env python3
"""Send a Meshtastic critical alert using ALERT_APP portnum + Priority.ALERT + bell char.

This combines three notification mechanisms:
  1. ALERT_APP portnum  — dedicated alert packet type, higher routing priority
  2. Priority.ALERT (110) — higher than normal messages (64), lower than ACK (120)
  3. ASCII bell (0x07)  — triggers External Notification Module on hardware nodes

Usage:
  python3 send_alert_critical.py "message text" [channel]

Examples:
  python3 send_alert_critical.py "ALARM: MOB!"
  python3 send_alert_critical.py "ALARM: MOB!" 1
"""

import sys
import time

sys.path.insert(0, '/home/pi/meshtastic/env/lib/python3.11/site-packages')

import meshtastic.serial_interface

PORT = '/dev/ttyACM1'

BELL = '\x07'

message = "ALERT"
channel = 0

if len(sys.argv) >= 2:
    message = sys.argv[1]
if len(sys.argv) >= 3:
    channel = int(sys.argv[2])

print(f"Connecting to {PORT} ...")
iface = meshtastic.serial_interface.SerialInterface(PORT)
time.sleep(1)

print(f"Sending critical alert: '{message}' on channel {channel}")
iface.sendAlert(BELL + message, channelIndex=channel)
time.sleep(2)

iface.close()
print("Done.")
