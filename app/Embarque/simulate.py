import argparse
import json
import random
import sys
import time
from pathlib import Path

import requests

SENSOR_TEMPLATE = [
    {"sensor_id": 1, "sensor_name": "Zone A — Nord", "zone": "Nord"},
    {"sensor_id": 2, "sensor_name": "Zone B — Centre", "zone": "Centre"},
    {"sensor_id": 3, "sensor_name": "Zone C — Sud", "zone": "Sud"},
    {"sensor_id": 4, "sensor_name": "Zone D — Est", "zone": "Est"},
]


def parse_args():
    parser = argparse.ArgumentParser(description='Simulate embedded sensor stream to Smart Irrigation API')
    parser.add_argument('--host', default='localhost', help='Back-end host (default: localhost)')
    parser.add_argument('--port', type=int, default=5000, help='Back-end port (default: 5000)')
    parser.add_argument('--interval', type=float, default=30.0, help='Seconds between each batch (default: 30)')
    parser.add_argument('--sensors', type=int, default=4, choices=range(1, 9), metavar='[1-8]', help='Number of sensors to simulate (default: 4)')
    parser.add_argument('--replay-file', type=str, default=None, help='Optional path to Data/data.json for replay mode')
    parser.add_argument('--jitter', type=float, default=0.1, help='Noise fraction for random mode (default: 0.1)')
    return parser.parse_args()


def build_api_url(host, port):
    return f'http://{host}:{port}/api/data'


def random_value(base, spread=5):
    return max(0.0, min(100.0, base + random.uniform(-spread, spread)))


def read_data_json(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f'{path} not found')
    with path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError('JSON replay file must be an array of entries')
    return data


def main():
    args = parse_args()
    api_url = build_api_url(args.host, args.port)

    print('Starting Embarque simulator')
    print('Backend:', api_url)
    print('Interval:', args.interval, 's')

    replay_data = []
    replay_index = 0

    if args.replay_file:
        replay_data = read_data_json(args.replay_file)
        print(f'Replay mode ON: {len(replay_data)} records loaded from {args.replay_file}')

    sensors = SENSOR_TEMPLATE[:args.sensors]

    # initial ambient values
    current = {s['sensor_id']: {'humidity': 60.0 - 15.0 * (s['sensor_id'] - 1), 'temperature': 19.0 + 2*(s['sensor_id']-1)} for s in sensors}

    while True:
        payloads = []

        if replay_data:
            # send entries in time order, cycling if reaches end
            for i in range(args.sensors):
                raw = replay_data[(replay_index + i) % len(replay_data)]
                payloads.append({
                    'sensor_id': raw.get('sensor_id'),
                    'sensor_name': raw.get('sensor_name'),
                    'zone': raw.get('zone'),
                    'humidity': float(raw.get('soil_humidity_%', raw.get('humidity', 0))),
                    'temperature': float(raw.get('temperature_C', raw.get('temperature', 0)))
                })
            replay_index = (replay_index + args.sensors) % len(replay_data)
        else:
            for sensor in sensors:
                sid = sensor['sensor_id']
                base = current[sid]
                new_hum = random_value(base['humidity'], spread=7 * (1 + args.jitter))
                new_tmp = max(-10.0, min(60.0, base['temperature'] + random.uniform(-1.8, 1.8)))
                current[sid]['humidity'] = new_hum
                current[sid]['temperature'] = new_tmp

                payloads.append({
                    'sensor_id': sid,
                    'sensor_name': sensor['sensor_name'],
                    'zone': sensor['zone'],
                    'humidity': round(new_hum, 2),
                    'temperature': round(new_tmp, 2),
                })

        for payload in payloads:
            try:
                r = requests.post(api_url, json=payload, timeout=8)
                if r.status_code == 200:
                    data = r.json()
                    print(f"[{payload['sensor_id']}] OK {payload['zone']} H={payload['humidity']} T={payload['temperature']} -> {data.get('recommendation')}")
                else:
                    print(f"[{payload['sensor_id']}] ERROR {r.status_code} {r.text}")
            except Exception as e:
                print(f"[{payload['sensor_id']}] REQUEST FAIL: {e}")

        print(f"Batch complete. Sleeping {args.interval}s...\n")
        time.sleep(args.interval)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nSimulator stopped by user')
        sys.exit(0)
