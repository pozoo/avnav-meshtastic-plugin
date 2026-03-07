#!/usr/bin/env python3
"""
Anchor-swing simulation for avnav-meshtastic-plugin testing.

Simulates a 20-minute anchor watch off Biograd na Moru (Croatia, Adriatic).
The yacht swings around a 50 m chain as a light afternoon Maestral shifts
from NW to WNW.  Every 60 s the script transmits all packet types that the
plugin can produce:

  • POSITION_APP         — lat/lon/SOG/heading/HDOP/sats/fix_quality
  • TELEMETRY_APP        — wind speed/direction/gust, pressure, anchor distance
  • TEXT_MESSAGE_APP     — simulation start/end announcements

Device:  /dev/ttyACM1   Channel: 0
"""

import sys
import math
import time
import random

sys.path.insert(0, '/home/pi/meshtastic/env/lib/python3.11/site-packages')

import meshtastic.serial_interface
from meshtastic import mesh_pb2, portnums_pb2
from meshtastic.protobuf import telemetry_pb2

# ── hardware ─────────────────────────────────────────────────────────────────
PORT    = '/dev/ttyACM0'
CHANNEL = 1

# ── anchor location ───────────────────────────────────────────────────────────
# Pašman Channel, directly off Biograd na Moru, Croatia
ANCHOR_LAT = 43.9385   # °N
ANCHOR_LON = 15.4310   # °E  (in the channel, ~700 m west of town pier)
CHAIN_M    = 50.0       # anchor chain length = maximum swing radius (metres)

# ── simulation schedule ───────────────────────────────────────────────────────
INTERVAL_S = 60        # seconds between transmissions
STEPS      = 20        # 20 × 60 s = 20 minutes

# ── earth geometry at anchor latitude ────────────────────────────────────────
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(ANCHOR_LAT))  # ≈ 80 230 m/°


# ─────────────────────────────────────────────────────────────────────────────
# Simulation model
# ─────────────────────────────────────────────────────────────────────────────

def bearing_delta(bearing_deg: float, distance_m: float):
    """(dlat, dlon) in degrees for a given bearing and distance from current pos."""
    b = math.radians(bearing_deg)
    return (
        math.cos(b) * distance_m / M_PER_DEG_LAT,
        math.sin(b) * distance_m / M_PER_DEG_LON,
    )


def simulate(step: int) -> dict:
    """
    Return a dict of all simulated sensor values for *step* (0 … STEPS-1).

    Wind model
    ----------
    A gusty summer Maestral swinging noticeably back and forth:
      - mean direction 305° (WNW), oscillating ±25° with a slow ~7-min period
        → total arc ~50°, boat sweeps a ~43 m chord at full scope
      - additional fast puff oscillation ±5° layered on top
      - mean slow veer from 305° → 295° over the 20 min run
      - speed oscillates gently 6 – 9 kt with small random noise
      - gusts 2 – 4 kt above mean

    Yacht position
    --------------
    The boat lies downwind from the anchor.  The slow, large wind-direction
    swing (±25°) sweeps the boat through a wide arc clearly visible on a map.
    A faster lateral sway (±25 % of chain) adds realistic pendulum motion.
    Chain scope (horizontal projection) varies 75 – 95 % with the gusts.
    """
    t = step / max(STEPS - 1, 1)   # normalised time 0.0 → 1.0

    # ── wind direction: mean 305° veering slowly to 295°, ±25° slow swing ─────
    # slow_swing: one full cycle ≈ 7 min (2.86 cycles over 20 min)
    slow_swing  = 25.0 * math.sin(2 * math.pi * t * 2.86)
    # fast puff wobble: ±5° at ~3 cycles over 20 min
    fast_wobble = 5.0  * math.sin(2 * math.pi * t * 3.7 + 0.9)
    mean_dir    = 305.0 - t * 10.0
    wind_dir    = (mean_dir + slow_swing + fast_wobble) % 360

    # ── wind speed: 7 kt base, ±1.5 kt slow swell, small random noise ────────
    wind_kt = 7.0 + 1.5 * math.sin(2 * math.pi * t * 1.8 + 0.4) + random.uniform(-0.4, 0.4)
    wind_kt = max(4.5, min(9.5, wind_kt))
    wind_ms = wind_kt * 0.514444

    gust_kt = wind_kt + random.uniform(2.0, 4.0)
    gust_ms = gust_kt * 0.514444

    # ── barometric pressure: 1016 hPa, barely drifts ─────────────────────────
    pressure = 1016.0 + 0.4 * math.sin(2 * math.pi * t * 0.3)

    # ── boat position relative to anchor ─────────────────────────────────────
    # Downwind direction (where the boat is pushed to)
    downwind_bearing = (wind_dir + 180.0) % 360.0

    # Chain scope shrinks a bit in gusts (catenary flattens), expands in lulls
    scope = 0.82 + 0.13 * math.sin(2 * math.pi * t * 3.0 + 1.1)
    scope = max(0.70, min(0.95, scope))
    along_m = CHAIN_M * scope

    # Lateral sway perpendicular to downwind axis (±25 % of chain)
    lateral_m = CHAIN_M * 0.25 * math.sin(2 * math.pi * t * 4.7 + 0.6)
    lateral_bearing = (downwind_bearing + 90.0) % 360.0

    dlat1, dlon1 = bearing_delta(downwind_bearing, along_m)
    dlat2, dlon2 = bearing_delta(lateral_bearing,  lateral_m)
    boat_lat = ANCHOR_LAT + dlat1 + dlat2
    boat_lon = ANCHOR_LON + dlon1 + dlon2

    # True distance from anchor (metres)
    dx = (boat_lat - ANCHOR_LAT) * M_PER_DEG_LAT
    dy = (boat_lon - ANCHOR_LON) * M_PER_DEG_LON
    anchor_dist_m = math.hypot(dx, dy)

    # ── COG/heading: bow into wind, tiny wandering ────────────────────────────
    hdg_deg = wind_dir + random.uniform(-3.0, 3.0)   # bow faces into Maestral
    hdg_deg = hdg_deg % 360

    # ── SOG: very low chain-snubbing drift ────────────────────────────────────
    sog_kt  = random.uniform(0.05, 0.30)
    sog_kmh = sog_kt * 1.852

    # ── GPS quality: good open-sky Adriatic view ──────────────────────────────
    hdop = round(0.85 + random.uniform(0.0, 0.25), 2)
    sats = random.choice([10, 10, 11, 11, 11, 12])

    return {
        'lat':           boat_lat,
        'lon':           boat_lon,
        'sog_kmh':       sog_kmh,
        'hdg_deg':       hdg_deg % 360,
        'hdop':          hdop,
        'sats':          sats,
        'wind_ms':       wind_ms,
        'wind_dir':      int(round(wind_dir)) % 360,
        'gust_ms':       gust_ms,
        'pressure':      pressure,
        'anchor_dist_m': anchor_dist_m,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Packet senders  (mirrors exact proto usage in plugin.py)
# ─────────────────────────────────────────────────────────────────────────────

def send_position(iface, d: dict):
    p = mesh_pb2.Position()
    p.latitude_i     = int(d['lat'] * 1e7)
    p.longitude_i    = int(d['lon'] * 1e7)
    p.precision_bits = 32
    p.ground_speed   = int(round(d['sog_kmh']))           # km/h integer
    p.ground_track   = int(round(d['hdg_deg'] * 100))     # 1/100 degrees
    p.HDOP           = int(round(d['hdop'] * 100))        # HDOP × 100
    p.sats_in_view   = d['sats']
    p.fix_quality    = 1                                   # 1 = GPS fix
    p.time           = int(time.time())
    iface.sendData(p, portNum=portnums_pb2.PortNum.POSITION_APP, channelIndex=CHANNEL)


def send_environment(iface, d: dict):
    env = telemetry_pb2.EnvironmentMetrics()
    env.wind_speed          = d['wind_ms']
    env.wind_direction      = d['wind_dir']
    env.wind_gust           = d['gust_ms']
    env.barometric_pressure = d['pressure']
    env.distance            = d['anchor_dist_m'] * 1000.0  # mm (as in plugin)

    tel = telemetry_pb2.Telemetry()
    tel.time = int(time.time())
    tel.environment_metrics.CopyFrom(env)
    iface.sendData(tel, portNum=portnums_pb2.PortNum.TELEMETRY_APP, channelIndex=CHANNEL)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    random.seed(42)   # reproducible run; remove for true randomness

    print(f"Connecting to Meshtastic on {PORT} …")
    iface = meshtastic.serial_interface.SerialInterface(PORT)
    time.sleep(2)
    print("Connected.\n")

    print("=" * 60)
    print(f"  Anchor: {ANCHOR_LAT:.4f}°N  {ANCHOR_LON:.4f}°E")
    print(f"          Pašman Channel, off Biograd na Moru, Croatia")
    print(f"  Chain:  {CHAIN_M:.0f} m swing radius")
    print(f"  Plan:   {STEPS} transmissions × {INTERVAL_S} s = {STEPS * INTERVAL_S // 60} min")
    print(f"  Wind:   Maestral ~7 kt from WNW, ±25° slow swing (~43 m arc)")
    print("=" * 60 + "\n")

    iface.sendText(
        f"\x07SIMULATION START – anchor off Biograd na Moru, chain {CHAIN_M:.0f} m, "
        f"20 min swing test",
        channelIndex=CHANNEL,
    )
    time.sleep(1)

    for step in range(STEPS):
        step_start = time.time()
        elapsed_min = step * INTERVAL_S / 60
        d = simulate(step)

        ts = time.strftime('%H:%M:%S')
        lat_i = int(d['lat'] * 1e7)
        lon_i = int(d['lon'] * 1e7)
        print(f"┌─ Step {step + 1:2d}/{STEPS}   T+{elapsed_min:.0f} min   {ts} ─────────────────────────")
        print(f"│  Position  : {d['lat']:.7f}°N  {d['lon']:.7f}°E"
              f"  (latitude_i={lat_i}  longitude_i={lon_i})")
        print(f"│  SOG       : {d['sog_kmh'] / 1.852:.2f} kt   "
              f"Hdg: {d['hdg_deg']:.0f}°   "
              f"HDOP: {d['hdop']:.2f}   Sats: {d['sats']}")
        print(f"│  Wind      : {d['wind_ms'] / 0.514444:.1f} kt  from {d['wind_dir']}°  "
              f"gust {d['gust_ms'] / 0.514444:.1f} kt")
        print(f"│  Pressure  : {d['pressure']:.1f} hPa")
        print(f"│  Anchor Δ  : {d['anchor_dist_m']:.1f} m  "
              f"({d['anchor_dist_m'] * 1000:.0f} mm sent in env packet)")

        ok_pos = ok_env = False
        try:
            send_position(iface, d)
            ok_pos = True
        except Exception as exc:
            print(f"│  ✗ position send failed: {exc}")

        time.sleep(0.8)  # brief gap between back-to-back packets

        try:
            send_environment(iface, d)
            ok_env = True
        except Exception as exc:
            print(f"│  ✗ environment send failed: {exc}")

        sent = []
        if ok_pos: sent.append("position")
        if ok_env: sent.append("environment")
        print(f"└─ Sent: {', '.join(sent) if sent else 'NOTHING (errors above)'}\n")

        # Sleep for the remainder of the 60 s interval
        if step < STEPS - 1:
            spent = time.time() - step_start
            wait  = max(0.0, INTERVAL_S - spent)
            time.sleep(wait)

    # Simulation complete
    iface.sendText("SIMULATION END – 20 min anchor swing complete", channelIndex=CHANNEL)
    time.sleep(2)
    iface.close()
    print("Done. Interface closed.")


if __name__ == '__main__':
    main()
