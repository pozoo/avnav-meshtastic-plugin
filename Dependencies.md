# Meshtastic AvNav Plugin — Python Dependencies

## Overview

The plugin runs inside **AvNav** on **Raspbian Bookworm**. AvNav loads its own Python environment first, then the plugin appends the venv (`/home/pi/meshtastic/env`) to `sys.path` to make the `meshtastic` package available.

**Important:** Python caches imported modules in `sys.modules`. Any package already imported by AvNav before the plugin runs will **not** be reloaded from the venv, even if a newer version is present there. The system (deb) version takes precedence for those packages.

---

## Direct Plugin Imports

The plugin scripts only directly import `meshtastic` and standard library modules:

```
meshtastic.serial_interface
meshtastic.mesh_pb2 / portnums_pb2
meshtastic.protobuf.telemetry_pb2
json, os, sys, threading, time, urllib.parse, urllib.request
```

All other third-party packages are indirect dependencies pulled in by `meshtastic` itself.

---

## Dependency Matrix

| pip package | Version in venv | Meshtastic requires | Bookworm deb | Deb version | Installed | Compatible |
|---|---|---|---|---|---|---|
| meshtastic | 2.7.7 | — | none | — | No | N/A |
| bleak | 2.1.1 | `>=0.22.3` | `python3-bleak` | 0.20.2 | No | No — too old |
| dbus-fast | 4.0.0 | *(bleak dep)* | `python3-dbus-fast` | 1.84.2 | No | No — too old |
| packaging | 24.2 | `>=24.0,<25.0` | `python3-packaging` | 23.0 | No | No — too old |
| protobuf | 7.34.0 | `>=4.21.12` | `python3-protobuf` | 3.21.12 | No | No — too old |
| pypubsub | 4.0.7 | `>=4.0.3,<5.0.0` | `python3-pubsub` | 4.0.3 | No | Yes |
| pyserial | 3.5 | `>=3.5,<4.0` | `python3-serial` | 3.5 | **Yes** | Yes |
| PyYAML | 6.0.3 | `>=6.0.1,<7.0.0` | `python3-yaml` | 6.0 | **Yes** | No — 6.0 < 6.0.1 |
| requests | 2.32.5 | `>=2.31.0,<3.0.0` | `python3-requests` | 2.28.1 | **Yes** | No — too old |
| tabulate | 0.9.0 | `>=0.9.0,<0.10.0` | `python3-tabulate` | 0.8.9 | No | No — too old |
| typing_extensions | 4.15.0 | *(no strict req)* | `python3-typing-extensions` | 4.4.0 | No | — |
| certifi | 2026.2.25 | *(requests dep)* | `python3-certifi` | 2022.9.24 | **Yes** | — |
| charset-normalizer | 3.4.4 | *(requests dep)* | `python3-charset-normalizer` | 3.0.1 | **Yes** | — |
| idna | 3.11 | *(requests dep)* | `python3-idna` | 3.3 | **Yes** | — |
| urllib3 | 2.6.3 | *(requests dep)* | `python3-urllib3` | 1.26.12 | **Yes** | — |

---

## Version Conflicts

### Critical — deb version does not meet meshtastic's requirement

| Package | Deb version | Required | Notes |
|---|---|---|---|
| bleak | 0.20.2 | `>=0.22.3` | Must come from venv |
| dbus-fast | 1.84.2 | — | Must come from venv |
| packaging | 23.0 | `>=24.0` | Must come from venv |
| protobuf | 3.21.12 | `>=4.21.12` | Must come from venv |
| tabulate | 0.8.9 | `>=0.9.0` | Must come from venv |

### Non-critical — deb version too old but working in practice

These packages are already imported by AvNav before the plugin loads. Due to Python's `sys.modules` caching, the system version is used at runtime even though the venv contains newer versions. The plugin currently works despite the version mismatch.

| Package | Deb version | Required | Risk |
|---|---|---|---|
| PyYAML | 6.0 | `>=6.0.1` | Borderline — one patch version below minimum |
| requests | 2.28.1 | `>=2.31.0` | Below minimum but functional in practice |
| certifi | 2022.9.24 | *(transitive)* | Low |
| charset-normalizer | 3.0.1 | *(transitive)* | Low |
| idna | 3.3 | *(transitive)* | Low |
| urllib3 | 1.26.12 | *(transitive)* | Low |

---

## Installation

### Install pip packages into the venv

```bash
source /home/pi/meshtastic/env/bin/activate
pip install -r requirements.txt
```

### Install available deb packages

```bash
xargs apt-get install -y < packages.txt
```

### Check reverse dependencies before removing a deb package

```bash
apt-cache rdepends --installed python3-requests
```
