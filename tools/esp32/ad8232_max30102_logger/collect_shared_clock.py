#!/usr/bin/env python3
"""Capture combined ESP32 ECG/PPG with both host and device timestamps."""
import argparse, csv, time, serial

p = argparse.ArgumentParser()
p.add_argument('--port', default='/dev/ttyUSB0')
p.add_argument('--seconds', type=float, default=60.0)
p.add_argument('--out', required=True)
a = p.parse_args()

ser = serial.Serial(a.port, 115200, timeout=0.5)
ser.dtr = True; ser.rts = True
time.sleep(0.15)
ser.dtr = False; ser.rts = False
end = time.monotonic() + a.seconds

with open(a.out, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['host_time_ns', 'device_time_us', 'ecg_adc', 'red', 'ir'])
    while time.monotonic() < end:
        line = ser.readline().decode('ascii', 'replace').strip()
        if not line.startswith('sample,'):
            continue
        fields = line.split(',')
        if len(fields) != 5:
            continue
        try:
            dev_us, ecg, red, ir = map(int, fields[1:])
        except ValueError:
            continue
        w.writerow([time.time_ns(), dev_us, ecg, red, ir])
ser.close()
