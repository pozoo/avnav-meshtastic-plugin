#!/usr/bin/env python3
"""
Send simulated barometric pressure at 1 Hz to a TCP endpoint
(default: navi42.local:34567).

Two sentences are sent each second with identical values:

  XDR  — parsed by AvNav: stores as gps.transducers.Barometer (Pa)
    $IIXDR,P,<bar>,B,Barometer*XX
    pressure in bar  (1013.2 hPa = 1.0132 bar)

  MDA  — parsed by Signal K: stores as environment.outside.pressure (Pa)
    $IIMDA,,[I],<bar>,B,,,,,,,,,,,,,,*XX
    pressure field 3 in bar, Signal K converts bar × 100000 → Pa

Pressure varies sinusoidally around 1013.2 hPa ± 2 hPa with a 60-second
period so the change is clearly visible in both displays.
"""

import socket
import time
import math

HOST = 'navi42.local'
PORT = 34567

BASE_HPA  = 1013.2   # hPa  (centre value)
SWING_HPA = 2.0      # hPa  (± amplitude)
PERIOD_S  = 60       # seconds per full sine cycle


def nmea_checksum(body: str) -> str:
    """XOR of all ASCII bytes between $ and * (exclusive)."""
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return '%02X' % cs


def sentence(body: str) -> bytes:
    return ('$%s*%s\r\n' % (body, nmea_checksum(body))).encode('ascii')


def make_xdr(hpa: float) -> bytes:
    """$IIXDR,P,<bar>,B,Barometer — AvNav stores as transducers.Barometer in Pa."""
    bar = hpa / 1000.0
    return sentence('IIXDR,P,%.5f,B,Barometer' % bar)


def make_mda(hpa: float) -> bytes:
    """$IIMDA,,,<bar>,B,... — Signal K stores as environment.outside.pressure in Pa."""
    bar = hpa / 1000.0
    # Fields: [inHg][I][bar][B][air_temp][C][water_temp][C][humidity]...(rest empty)
    # Minimum valid MDA with only barometric pressure:
    body = 'IIMDA,,,%.5f,B,,C,,C,,,,,T,,M,,N,,M' % bar
    return sentence(body)


def main():
    print(f'Connecting to {HOST}:{PORT} …')
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    print('Connected.\n')

    step = 0
    try:
        while True:
            t = step / PERIOD_S
            hpa = BASE_HPA + SWING_HPA * math.sin(2 * math.pi * t)
            xdr = make_xdr(hpa)
            mda = make_mda(hpa)
            sock.sendall(xdr + mda)
            print(f'  {hpa:.2f} hPa  |  {xdr.decode().strip()}')
            print(f'           |  {mda.decode().strip()}')
            step += 1
            time.sleep(1.0)
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        sock.close()


if __name__ == '__main__':
    main()


if __name__ == '__main__':
    main()
