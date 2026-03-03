#!/usr/bin/env python3
"""Send a Meshtastic alert/bell message from the command line.

The ASCII bell character (0x07) embedded in the message text triggers:
  - Alert highlight in the iOS/Android Meshtastic app
  - External Notification Module on receiving nodes (buzzer/LED) if configured

Usage:
  python3 send_alert.py [--no-bell] "message text" [channel]

Examples:
  python3 send_alert.py "ALARM: MOB!"
  python3 send_alert.py "ALARM: MOB!" 1
  python3 send_alert.py --no-bell "Info: all good" 1
"""

import sys
import time

sys.path.insert(0, '/home/pi/meshtastic/env/lib/python3.11/site-packages')

import meshtastic.serial_interface

PORT = '/dev/ttyACM1'

BELL = '\x07'  # ASCII bell character — triggers alert in app and ext. notification module

# Parse --no-bell flag
args = sys.argv[1:]
send_bell = True
if '--no-bell' in args:
    send_bell = False
    args.remove('--no-bell')

message = args[0] if len(args) >= 1 else "ALERT"
channel = int(args[1]) if len(args) >= 2 else 0

alert_text = (BELL + message) if send_bell else message

print(f"Connecting to {PORT} ...")
iface = meshtastic.serial_interface.SerialInterface(PORT)
time.sleep(1)

print(f"Sending {'alert (with bell)' if send_bell else 'message (no bell)'}: '{message}' on channel {channel}")
iface.sendText(alert_text, channelIndex=channel)
time.sleep(2)

iface.close()
print("Done.")
