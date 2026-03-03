#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pip3 install -t "$SCRIPT_DIR/meshtastic/lib" -r "$SCRIPT_DIR/requirements.txt"