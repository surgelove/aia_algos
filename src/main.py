import argparse
import json
import time
from datetime import datetime
from typing import Optional

import redis

import algo
import broker

REDIS_HOST = "localhost"
REDIS_PORT = 6379
STREAM_PREFIX = "prices:"
SIGNALS_STREAM = "signals"

def main():
    parser = argparse.ArgumentParser(
        description="Listen to Redis price stream or per-key price messages and process with TimeBasedStreamingMA."
    )
    parser.add_argument("--instrument", type=str, default="USD_CAD", help="Instrument to listen to (e.g. USD_CAD)")
    parser.add_argument("--db", type=int, default=0, help="Redis DB number")
    parser.add_argument("--ttl", type=int, default=None, help="TTL in seconds for signals keys (optional)")
    args = parser.parse_args()

    with open('config/secrets.json', 'r') as f:
        credentials = json.load(f)['oanda']

    instrument = args.instrument
    ttl = args.ttl
    precision = broker.get_instrument_precision(credentials, instrument)
    print(precision)
    purple = algo.Algo(base_interval='15min', slow_interval='30min', aspr_interval='3min', peak_interval='2min')

    # connect to the same Redis DB you used to store the key (default 0)
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=args.db, decode_responses=True)
    stream_key = f"{STREAM_PREFIX}{instrument}"

    # print(stream_key)
    # for v in r.scan_iter(f"{stream_key}:*"):
    #     print(v)

    # read existing keys and track seen ones
    seen = set()
    for key in r.scan_iter(f"{stream_key}:*"):
        seen.add(key)
        print(f"found key={key!r}")
        raw = r.get(key)
        print(f" raw value: {raw!r}")

    print("waiting for new keys... (Ctrl-C to exit)")

    # stay in main and wait for new keys to appear
    try:
        while True:
            # small sleep to avoid tight polling loop
            time.sleep(1)
            for key in r.scan_iter(f"{stream_key}:*"):
                if key in seen:
                    continue
                seen.add(key)
                # print(f"new key={key!r}")
                raw = r.get(key)
                # print(f" raw value: {raw!r}")

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError as e:
                    print(f" JSON decode error for key={key}: {e}")
                    continue
                # print(data)

                # convert string timestamp to datetime
                timestamp = data.get('timestamp')
                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp)
                    except ValueError:
                        try:
                            timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f")
                        except ValueError as e:
                            print(f" failed to parse timestamp for key={key}: {e}")
                            continue
                price = float(data['price'])
                
                return_dict = purple.process_row(timestamp, price, precision, say=False)
                # reconvert timestamp in return_dict back to ISO string
                if isinstance(return_dict, dict):
                    ts_val = return_dict.get('timestamp')
                    if ts_val is not None and not isinstance(ts_val, str):
                        try:
                            # handle pandas.Timestamp
                            if hasattr(ts_val, 'to_pydatetime'):
                                ts_dt = ts_val.to_pydatetime()
                            else:
                                ts_dt = ts_val
                            if isinstance(ts_dt, datetime):
                                return_dict['timestamp'] = ts_dt.isoformat()
                            else:
                                return_dict['timestamp'] = str(ts_val)
                        except Exception:
                            return_dict['timestamp'] = str(ts_val)

                # Add to return_dict instrument after timestamp
                if isinstance(return_dict, dict):
                    # preserve order: timestamp (0), instrument (1), then rest
                    if 'timestamp' in return_dict:
                        new_dict = {}
                        new_dict['timestamp'] = return_dict['timestamp']
                        new_dict['instrument'] = instrument
                        for k, v in return_dict.items():
                            if k in ('timestamp', 'instrument'):
                                continue
                            new_dict[k] = v
                        return_dict = new_dict
                    else:
                        # no timestamp present, create dict with instrument first
                        new_dict = {'instrument': instrument}
                        for k, v in return_dict.items():
                            new_dict[k] = v
                        return_dict = new_dict


                print(type(return_dict))
                print(return_dict)

                # Put the return_dict on the redis stream with prefix algos:
                if isinstance(return_dict, dict):
                    algos_key = f"algos:{instrument}:{return_dict.get('timestamp')}"
                    # set with TTL if provided
                    if ttl is not None:
                        r.set(algos_key, json.dumps(return_dict), ex=ttl)
                    else:
                        r.set(algos_key, json.dumps(return_dict))
                    print(f"wrote algos key={algos_key!r}")

    except KeyboardInterrupt:
        print("exiting")

if __name__ == "__main__":
    main()

