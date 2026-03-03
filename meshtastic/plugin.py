# -*- coding: utf-8 -*-
# AVnav Meshtastic Plugin
# Sends GPS telemetry and alarm notifications via a Meshtastic device over USB.

import sys
import os
import time
import threading
import json
import urllib.request
import urllib.parse

# Add the lib/ folder next to this file so meshtastic is importable without a
# system install.  Using append (not insert) so system packages still take
# priority for everything AVnav already uses.
_LIB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib')
if _LIB_PATH not in sys.path:
    sys.path.append(_LIB_PATH)

import serial.tools.list_ports as _list_ports

def _port_from_usbid(usbid):
    """
    Derive the /dev/tty* path from an AVnav USB interface ID (e.g. '1-2:1.0').
    Uses pyserial's port listing so no sysfs parsing is needed.
    Returns None if no matching port is found.
    """
    for port in _list_ports.comports():
        if port.location and port.location.endswith(usbid):
            return port.device
    return None

# Try importing meshtastic — kept deferred so AVnav can still load the plugin
# and report an error on the status page rather than crashing at import time.
_MESHTASTIC_AVAILABLE = False
_MESHTASTIC_IMPORT_ERROR = ''
try:
    import meshtastic
    import meshtastic.serial_interface
    from meshtastic.mesh_interface import MeshInterface
    from meshtastic import mesh_pb2, portnums_pb2
    from meshtastic.protobuf import telemetry_pb2
    _MESHTASTIC_AVAILABLE = True
except Exception as _e:
    _MESHTASTIC_IMPORT_ERROR = str(_e)

# Optional: import AVNApi for IDE autocompletion only — not required at runtime.
try:
    from avnav_api import AVNApi
except Exception:
    pass

# ---------------------------------------------------------------------------
# AVnav data key names 
# ---------------------------------------------------------------------------
AVNAV_LAT       = 'gps.lat'                                         # latitude (degrees)
AVNAV_LON       = 'gps.lon'                                         # longitude (degrees)
AVNAV_SOG       = 'gps.speed'                                       # speed over ground in m/s; plugin converts ×3.6 → km/h
AVNAV_HDT       = 'gps.headingTrue'                                 # heading, seems is not shown in meshtasitc app
AVNAV_HDT_ALT   = 'gps.sail_instrument.HDT'                         # heading, seems is not shown in meshtasitc app

AVNAV_HDOP      = 'gps.signalk.navigation.gnss.horizontalDilution'  # dimensionless ratio
AVNAV_SATS      = 'gps.satUsed'                                     # satellites used (integer)

AVNAV_WIND_SPD      = 'gps.trueWindSpeed'                           # true wind speed in knots; plugin converts ×0.5144 → m/s
AVNAV_WIND_SPD_ALT  = 'gps.sail_instrument.TWS'                     # alternate key tried if AVNAV_WIND_SPD returns nothing
AVNAV_WIND_DIR      = 'gps.trueWindDirection'                       # true wind direction, degrees
AVNAV_WIND_DIR_ALT  = 'gps.sail_instrument.TWD'                     # alternate key tried if AVNAV_WIND_DIR returns nothing 
AVNAV_WIND_GUST = 'environment.wind.gustTrue'                       # TODO track max gusts in sailinstrument and report here
AVNAV_PRESSURE  = 'gps.signalk.environment.outside.pressure'        # Signal K stores pressure in Pa; plugin converts ÷100 → hPa

# anchor.distance / anchor.direction / anchor.watchDistance are JavaScript-only store keys
# (computed in the browser by navdata.js from leg.from + current GPS position).
# Anchor distance is read directly from AVNRouter in-process via _get_anchor_distance_m().
# ---------------------------------------------------------------------------


class Plugin(object):

    @classmethod
    def pluginInfo(cls):
        return {
            'description': 'Send AVnav GPS telemetry and alarm alerts via Meshtastic over USB',
            'data': []
        }

    def __init__(self, api):
        """
        Initialise the plugin. Must not start threads here.
        @param api: AVNApi instance
        @type  api: AVNApi
        """
        self.api = api
        self._interface = None          # meshtastic SerialInterface
        self._interface_lock = threading.Lock()
        self._alarm_last_sent = {}      # alarm name -> monotonic timestamp of last send
        self._alarm_silenced = False         # when True, alarm forwarding is paused
        self._last_telemetry = 0.0      # monotonic timestamp of last telemetry send
        self._last_environment = 0.0    # monotonic timestamp of last environment send
        self._last_debug_send = 0.0     # monotonic timestamp of last debug counter send
        self._debug_counter = 0         # incrementing debug counter
        self._port_at_connect = None    # port used when _interface was opened

        # Register editable parameters (visible on AVnav status page).
        self.api.registerEditableParameters(
            [
                {
                    'name': 'usbid',
                    'type': 'STRING',
                    'default': '1-2:1.0',
                    'description': 'AVnav USB port ID (from status page) — prevents AVnav treating device as NMEA source'
                },
                {
                    'name': 'channel',
                    'type': 'NUMBER',
                    'default': '0',
                    'description': 'Meshtastic channel index for outgoing messages'
                },
                {
                    'name': 'pos_interval',
                    'type': 'NUMBER',
                    'default': '60',
                    'description': 'Seconds between GPS position broadcasts (0 to disable)'
                },
                {
                    'name': 'alarm_interval',
                    'type': 'NUMBER',
                    'default': '60',
                    'description': 'Seconds between repeated sends of each active alarm (0 to disable alarm forwarding)'
                },
                {
                    'name': 'env_interval',
                    'type': 'NUMBER',
                    'default': '120',
                    'description': 'Seconds between environment telemetry sends (wind/pressure); 0 to disable'
                },
                {
                    'name': 'debug_interval',
                    'type': 'NUMBER',
                    'default': '0',
                    'description': 'Minutes between debug counter messages (0 to disable)'
                },
                {
                    'name': 'test_mode',
                    'type': 'BOOLEAN',
                    'default': False,
                    'description': 'Use hardcoded test values for position and environment instead of live AVnav data'
                },
            ],
            self._on_config_change
        )

        # Allow the plugin to be enabled/disabled at runtime.
        self.api.registerRestart(self.stop)

        # Tell AVnav not to treat the Meshtastic USB port as a NMEA serial reader.
        usbid = self.api.getConfigValue('usbid', '1-2:1.0')
        if usbid:
            try:
                self.api.registerUsbHandler(usbid, self._on_usb)
                self.api.log("Registered USB handler for port id '%s'", usbid)
            except Exception as e:
                self.api.error("Could not register USB handler for '%s': %s", usbid, str(e))

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def _on_config_change(self, newValues):
        """Called by AVnav when editable parameters are modified at runtime."""
        self.api.saveConfigValues(newValues)
        if 'usbid' in newValues:
            self.api.log("Port/usbid changed — disconnecting for reconnect")
            self._disconnect()

    def _get_bool_config(self, name):
        """Read a BOOLEAN config value — AVnav returns it as a string 'True'/'False'."""
        val = self.api.getConfigValue(name)
        if isinstance(val, str):
            return val.lower() in ('true', '1', 'yes')
        return bool(val)

    def _get_config(self):
        """Read current config values with safe defaults."""
        try:
            interval = int(self.api.getConfigValue('pos_interval', '60') or 60)
        except (TypeError, ValueError):
            interval = 60
        try:
            channel = int(self.api.getConfigValue('channel', '0') or 0)
        except (TypeError, ValueError):
            channel = 0
        try:
            alarm_interval = int(self.api.getConfigValue('alarm_interval', '60') or 60)
        except (TypeError, ValueError):
            alarm_interval = 60
        try:
            debug_mins = int(self.api.getConfigValue('debug_interval', '0') or 0)
        except (TypeError, ValueError):
            debug_mins = 0
        try:
            env_interval = int(self.api.getConfigValue('env_interval', '0') or 0)
        except (TypeError, ValueError):
            env_interval = 0
        usbid = self.api.getConfigValue('usbid', '1-2:1.0') or '1-2:1.0'
        port = _port_from_usbid(usbid)
        return {
            'port': port,
            'pos_interval': max(0, interval),
            'alarm_interval': max(0, alarm_interval),
            'env_interval': max(0, env_interval),
            'channel': max(0, channel),
            'debug_interval': max(0, debug_mins) * 60,
            'test_mode': self._get_bool_config('test_mode'),
        }

    # ------------------------------------------------------------------
    # USB hot-plug callback
    # ------------------------------------------------------------------

    def _on_usb(self, device_path):
        """Called by AVnav when the registered USB device appears."""
        self.api.log("USB device detected at %s", device_path)
        # The run() loop will reconnect automatically on next iteration.
        self._disconnect()

    # ------------------------------------------------------------------
    # Meshtastic connection management
    # ------------------------------------------------------------------

    def _connect(self, port):
        """Open a SerialInterface to the Meshtastic device. Returns True on success."""
        if not port:
            self.api.error("Could not find serial port for usbid '%s'", self.api.getConfigValue('usbid', ''))
            self.api.setStatus('ERROR', 'Device not found — check usbid config')
            return False
        self.api.log("Connecting to Meshtastic at %s", port)
        self.api.setStatus('STARTED', 'Connecting to ' + port)
        try:
            iface = meshtastic.serial_interface.SerialInterface(port)
            with self._interface_lock:
                self._interface = iface
                self._port_at_connect = port
            self.api.log("Connected to Meshtastic at %s", port)
            self.api.setStatus('NMEA', 'Connected to ' + port)
            return True
        except Exception as e:
            self.api.error("Failed to connect to Meshtastic at %s: %s", port, str(e))
            self.api.setStatus('ERROR', 'Connect failed: ' + str(e))
            return False

    def _disconnect(self):
        """Close the SerialInterface if open."""
        with self._interface_lock:
            iface = self._interface
            self._interface = None
            self._port_at_connect = None
        if iface is not None:
            try:
                iface.close()
                self.api.log("Meshtastic interface closed")
            except Exception as e:
                self.api.debug("Error closing Meshtastic interface: %s", str(e))

    def _is_connected(self):
        with self._interface_lock:
            return self._interface is not None

    def _send_text(self, msg, channel):
        """
        Send a text message via Meshtastic on the given channel.
        Returns True on success, False on failure (also disconnects on failure).
        """
        with self._interface_lock:
            iface = self._interface
        if iface is None:
            return False
        try:
            iface.sendText(msg, channelIndex=channel)
            self.api.debug("Sent: %s", msg)
            return True
        except Exception as e:
            self.api.error("Failed to send message '%s': %s", msg, str(e))
            self._disconnect()
            return False

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    # Test-mode fixed values for position
    _TEST_LAT        = 51.08100   # degrees
    _TEST_LON        = 14.54533   # degrees
    _TEST_SOG_KMH    = 9.26       # km/h  (~5 kt)
    _TEST_COG_DEG    = 270.0      # degrees true
    _TEST_HDOP       = 1.2
    _TEST_SATS       = 8
    _TEST_FIX        = 1          # 1 = GPS fix

    # Test-mode fixed values for environment
    _TEST_WIND_MS    = 5.144      # m/s  (~10 kt)
    _TEST_WIND_DIR   = 270        # degrees
    _TEST_WIND_GUST  = 7.716      # m/s  (~15 kt)
    _TEST_PRESSURE        = 1013.2     # hPa
    _TEST_ANCHOR_DIST_MM = 25000.0    # mm  (~25 m)

    def _read_float(self, key, default=0.0):
        """Safely read a float AVnav value; returns default if key is None or invalid."""
        try:
            v = self.api.getSingleValue(key)
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    def _read_int(self, key, default=0):
        """Safely read an int AVnav value; returns default if key is None or invalid."""
        try:
            v = self.api.getSingleValue(key)
            return int(float(v)) if v is not None else default
        except (TypeError, ValueError):
            return default

    def _get_anchor_distance_m(self):
        """
        Return the current anchor watch distance in metres by reading the
        AVNRouter leg object directly inside the server process — no HTTP.
        Returns None when anchor watch is not active or data is unavailable.
        """
        try:
            from avnav_worker import AVNWorker
            from avnav_util import AVNUtil
            router = AVNWorker.findHandlerByName("AVNRouter")
            if router is None:
                return None
            leg = router.getCurrentLeg()
            if leg is None or not leg.isAnchorWatch():
                return None
            from_wp = leg.getFrom()
            if from_wp is None:
                return None
            anchor_lat = from_wp.get('lat')
            anchor_lon = from_wp.get('lon')
            if anchor_lat is None or anchor_lon is None:
                return None
            gps_lat = self.api.getSingleValue(AVNAV_LAT)
            gps_lon = self.api.getSingleValue(AVNAV_LON)
            if gps_lat is None or gps_lon is None:
                return None
            # Use the same distance function as the router itself (great circle)
            return AVNUtil.distanceM(
                (float(gps_lat), float(gps_lon)),
                (float(anchor_lat), float(anchor_lon)),
            )
        except Exception as e:
            self.api.debug("Anchor distance via router failed: %s", str(e))
            return None

    def _get_value_with_fallback(self, primary, alternate):
        """
        Read an AVnav value from *primary*; if that returns None and *alternate*
        is a non-empty string, try *alternate* instead.  Returns None when both
        keys yield nothing.
        """
        v = self.api.getSingleValue(primary) if primary else None
        if v is None and alternate:
            v = self.api.getSingleValue(alternate)
        return v

    def _send_position_packet(self, channel, test_mode=False):
        """
        Send a Meshtastic POSITION_APP packet from current AVnav GPS data.
        All navigation fields (SOG, COG, HDOP, sats, fix quality) are included.
        Returns True on success, False if no GPS fix (live mode) or send failed.
        On send failure the interface is disconnected so the run() loop
        will reconnect on the next iteration.
        """
        if test_mode:
            lat        = self._TEST_LAT
            lon        = self._TEST_LON
            sog_kmh    = self._TEST_SOG_KMH
            cog_deg    = self._TEST_COG_DEG
            hdop       = self._TEST_HDOP
            sats       = self._TEST_SATS
            fix_quality = self._TEST_FIX
            self.api.log(
                "TEST MODE position: lat=%.5f lon=%.5f sog=%.1f km/h cog=%.0f° hdop=%.1f sats=%d",
                lat, lon, sog_kmh, cog_deg, hdop, sats
            )
        else:
            lat = self.api.getSingleValue(AVNAV_LAT)
            lon = self.api.getSingleValue(AVNAV_LON)
            # gps.valid is JavaScript-only; derive fix quality from lat/lon presence
            fix_quality = 1 if (lat is not None and lon is not None) else 0
            if lat is None or lon is None:
                return False
            lat  = float(lat)
            lon  = float(lon)
            # SOG: AVnav gives m/s; firmware Position.ground_speed uses km/h
            sog_kmh     = self._read_float(AVNAV_SOG,  0.0) * 3.6
            hdt_raw     = self._get_value_with_fallback(AVNAV_HDT, AVNAV_HDT_ALT)
            cog_deg     = float(hdt_raw) if hdt_raw is not None else 0.0
            hdop        = self._read_float(AVNAV_HDOP, 0.0)
            sats        = self._read_int(AVNAV_SATS,   0)

        with self._interface_lock:
            iface = self._interface
        if iface is None:
            return False
        try:
            p = mesh_pb2.Position()
            p.latitude_i   = int(lat * 1e7)
            p.longitude_i  = int(lon * 1e7)
            p.precision_bits = 32
            p.ground_speed = int(round(sog_kmh))          # km/h integer
            p.ground_track = int(round(cog_deg * 100))    # 1/100 degrees
            p.HDOP         = int(round(hdop * 100))       # HDOP × 100
            p.sats_in_view = sats
            p.fix_quality  = fix_quality
            p.time         = int(time.time())
            iface.sendData(
                p,
                portNum=portnums_pb2.PortNum.POSITION_APP,
                channelIndex=channel,
            )
            self.api.log(
                "Position sent: lat=%.5f lon=%.5f sog=%.1fkm/h cog=%.0f° "
                "hdop=%.1f sats=%d fix=%d",
                lat, lon, sog_kmh, cog_deg, hdop, sats, fix_quality
            )
            return True
        except Exception as e:
            self.api.error("Failed to send position packet: %s", str(e))
            self._disconnect()
            return False

    def _send_environment_packet(self, channel, test_mode=False):
        """
        Send a Meshtastic TELEMETRY_APP / EnvironmentMetrics packet from
        current AVnav wind and pressure data.
        Returns True on success.  Returns False (without disconnecting) if no
        data is available in live mode.  Disconnects and returns False on
        send failure.
        """
        if test_mode:
            wind_ms        = self._TEST_WIND_MS
            wind_dir       = self._TEST_WIND_DIR
            gust_ms        = self._TEST_WIND_GUST
            pressure       = self._TEST_PRESSURE
            anchor_dist_mm = self._TEST_ANCHOR_DIST_MM
            self.api.log(
                "TEST MODE environment: wind=%.2f m/s dir=%d° gust=%.2f m/s pressure=%.1f hPa anchor=%.0f mm",
                wind_ms, wind_dir, gust_ms, pressure, anchor_dist_mm
            )
        else:
            # Wind speed: AVnav gives knots; EnvironmentMetrics expects m/s
            KNOTS_TO_MS = 0.5144
            wind_kt_raw = self._get_value_with_fallback(AVNAV_WIND_SPD, AVNAV_WIND_SPD_ALT)
            wind_ms = float(wind_kt_raw) * KNOTS_TO_MS if wind_kt_raw is not None else None

            gust_kt_raw = self.api.getSingleValue(AVNAV_WIND_GUST)
            gust_ms = float(gust_kt_raw) * KNOTS_TO_MS if gust_kt_raw is not None else None

            dir_raw  = self._get_value_with_fallback(AVNAV_WIND_DIR, AVNAV_WIND_DIR_ALT)
            wind_dir = int(float(dir_raw)) if dir_raw is not None else None

            pres_raw = self.api.getSingleValue(AVNAV_PRESSURE)
            # Signal K pressure is in Pascals; convert to hPa (÷100)
            pressure = float(pres_raw) / 100.0 if pres_raw is not None else None

            # Anchor distance: read from AVNRouter in-process; EnvironmentMetrics.distance expects mm
            anchor_m = self._get_anchor_distance_m()
            anchor_dist_mm = anchor_m * 1000.0 if anchor_m is not None else None

            # Need at least one field to be worth sending
            if wind_ms is None and wind_dir is None and gust_ms is None and pressure is None and anchor_dist_mm is None:
                self.api.debug("No environment data available — skipping")
                return False

        with self._interface_lock:
            iface = self._interface
        if iface is None:
            return False
        try:
            env = telemetry_pb2.EnvironmentMetrics()
            if wind_ms        is not None:  env.wind_speed          = wind_ms
            if wind_dir       is not None:  env.wind_direction      = wind_dir
            if gust_ms        is not None:  env.wind_gust           = gust_ms
            if pressure       is not None:  env.barometric_pressure = pressure
            if anchor_dist_mm is not None:  env.distance            = anchor_dist_mm

            telemetry = telemetry_pb2.Telemetry()
            telemetry.time = int(time.time())
            telemetry.environment_metrics.CopyFrom(env)

            iface.sendData(
                telemetry,
                portNum=portnums_pb2.PortNum.TELEMETRY_APP,
                channelIndex=channel,
            )
            self.api.log(
                "Environment sent: wind=%s m/s dir=%s° gust=%s m/s pressure=%s hPa anchor=%s mm",
                '%.2f' % wind_ms        if wind_ms        is not None else 'N/A',
                '%d'   % wind_dir       if wind_dir       is not None else 'N/A',
                '%.2f' % gust_ms        if gust_ms        is not None else 'N/A',
                '%.1f' % pressure       if pressure       is not None else 'N/A',
                '%.0f' % anchor_dist_mm if anchor_dist_mm is not None else 'N/A',
            )
            return True
        except Exception as e:
            self.api.error("Failed to send environment packet: %s", str(e))
            self._disconnect()
            return False

    # ------------------------------------------------------------------
    # Alarm state — polled in-process from AVNAlarmHandler each loop cycle
    # ------------------------------------------------------------------

    def _get_running_alarm_names(self):
        """
        Return a set of currently active alarm names by querying AVNAlarmHandler
        directly in-process.  Returns an empty set on any error.
        """
        try:
            from avnav_worker import AVNWorker
            alarm_handler = AVNWorker.findHandlerByName("AVNAlarmHandler")
            if alarm_handler is not None:
                return set(alarm_handler.getRunningAlarmNames())
        except Exception as e:
            self.api.debug("In-process alarm query failed: %s", str(e))
        return set()

    # ------------------------------------------------------------------
    # Incoming Meshtastic message handler
    # ------------------------------------------------------------------

    def _on_message_received(self, packet, interface):
        """
        Called by the meshtastic pubsub bus for every received TEXT_MESSAGE_APP packet.
        Handles: 'alarm silent', 'alarm active', 'alarm status' commands.
        """
        try:
            text = (packet.get('decoded', {}).get('text') or '').strip().lower()
            sender = packet.get('fromId')
            cfg = self._get_config()
            if text == 'alarm silent':
                self._alarm_silenced = True
                self.api.log("Alarm forwarding silenced by remote command from %s", sender)
                self._send_text('Alarm forwarding: SILENCED', cfg['channel'])
            elif text == 'alarm active':
                self._alarm_silenced = False
                self.api.log("Alarm forwarding re-activated by remote command from %s", sender)
                self._send_text('Alarm forwarding: ACTIVE', cfg['channel'])
            elif text == 'alarm status':
                status = 'SILENCED' if self._alarm_silenced else 'ACTIVE'
                self._send_text('Alarm forwarding: %s' % status, cfg['channel'])
            elif text == 'help':
                self._send_text('Commands:\nalarm silent|active|status\nhelp', cfg['channel'])
        except Exception as e:
            self.api.debug("Error handling received message: %s", str(e))

    # ------------------------------------------------------------------
    # Main plugin thread
    # ------------------------------------------------------------------

    def run(self):
        """Main plugin loop — runs in its own thread."""
        if not _MESHTASTIC_AVAILABLE:
            msg = 'meshtastic library not available: ' + _MESHTASTIC_IMPORT_ERROR
            self.api.error(msg)
            self.api.setStatus('ERROR', msg)
            return

        self.api.setStatus('STARTED', 'Initialising')
        self.api.log("Meshtastic bridge plugin started")

        try:
            from pubsub import pub
            pub.subscribe(self._on_message_received, "meshtastic.receive.text")
            self.api.log("Subscribed to incoming Meshtastic text messages")
        except Exception as e:
            self.api.debug("Could not subscribe to meshtastic messages: %s", str(e))

        while not self.api.shouldStopMainThread():
            cfg = self._get_config()

            # --- Ensure connected ---
            if not self._is_connected():
                if not self._connect(cfg['port']):
                    # Back off before retrying to avoid log spam
                    for _ in range(15):
                        if self.api.shouldStopMainThread():
                            return
                        time.sleep(1)
                    continue

            now = time.monotonic()

            # --- Telemetry (position packet) ---
            interval = cfg['pos_interval']
            if interval > 0 and (now - self._last_telemetry) >= interval:
                sent = self._send_position_packet(cfg['channel'], test_mode=cfg['test_mode'])
                if sent:
                    self._last_telemetry = now
                elif not self._is_connected():
                    pass  # send failed; reconnect next iteration
                else:
                    # Still connected but no GPS fix
                    self.api.debug("No GPS fix — skipping telemetry")
                    # Advance timestamp to avoid retrying every second when no fix
                    self._last_telemetry = now

            # --- Environment telemetry ---
            env_interval = cfg['env_interval']
            if env_interval > 0 and (now - self._last_environment) >= env_interval:
                sent = self._send_environment_packet(cfg['channel'], test_mode=cfg['test_mode'])
                if sent:
                    self._last_environment = now
                elif not self._is_connected():
                    pass  # send failed; reconnect next iteration
                else:
                    # No data available yet — advance timestamp to avoid retrying every second
                    self._last_environment = now

            # --- Alarm forwarding ---
            alarm_interval = cfg['alarm_interval']
            if alarm_interval > 0 and not self._alarm_silenced:
                current_alarms = self._get_running_alarm_names()
                for name in current_alarms:
                    last_sent = self._alarm_last_sent.get(name, 0.0)
                    if (now - last_sent) >= alarm_interval:
                        alert = '\aALARM: %s' % name
                        self.api.log("Sending alarm: %s", name)
                        if self._send_text(alert, cfg['channel']):
                            self._alarm_last_sent[name] = now
                # Clear repeat timers for alarms that have stopped
                for name in list(self._alarm_last_sent.keys()):
                    if name not in current_alarms:
                        del self._alarm_last_sent[name]

            # --- Debug counter ---
            debug_interval = cfg['debug_interval']
            if debug_interval > 0 and (now - self._last_debug_send) >= debug_interval:
                self._debug_counter += 1
                debug_msg = 'DEBUG: counter=%d' % self._debug_counter
                self.api.log("Sending debug counter: %d", self._debug_counter)
                if self._send_text(debug_msg, cfg['channel']):
                    self._last_debug_send = now

            time.sleep(1)

        # Clean shutdown
        self._disconnect()
        self.api.log("Meshtastic bridge plugin stopped")

    def stop(self):
        """Called by AVnav when the plugin is disabled or AVnav is shutting down."""
        try:
            from pubsub import pub
            pub.unsubscribe(self._on_message_received, "meshtastic.receive.text")
        except Exception:
            pass
        self._disconnect()
