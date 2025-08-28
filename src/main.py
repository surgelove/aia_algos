import argparse
import json
import time
from datetime import datetime
from typing import Optional

import aia_utilities as au
# import aia_utiilities_test as au

import algo
import broker

REDIS_HOST = "localhost"
REDIS_PORT = 6379
PREFIX_INPUT = "prices"
PREFIX_OUTPUT = "algos"

def process(row, algo, instrument, precision):

    # convert string timestamp to datetime
    timestamp = au.string_to_datetime(row.get('timestamp'))
    price = float(row['price'])

    return_dict = algo.process_row(timestamp, price, precision, say=False)

    timestamp = au.datetime_to_string(return_dict.get('timestamp'))
    return_dict['timestamp'] = timestamp

    # Add to return_dict instrument after timestamp
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
    
    return return_dict


def main():
    parser = argparse.ArgumentParser(
        description="Listen to Redis price stream or per-key price messages and process with TimeBasedStreamingMA."
    )
    parser.add_argument("--instrument", type=str, default="USD_CAD", help="Instrument to listen to (e.g. USD_CAD)")
    parser.add_argument("--db", type=int, default=0, help="Redis DB number")
    parser.add_argument("--ttl", type=int, default=120, help="TTL in seconds for signals keys (optional)")
    args = parser.parse_args()

    with open('config/secrets.json', 'r') as f:
        credentials = json.load(f)['oanda']

    instrument = args.instrument
    ttl = args.ttl
    precision = broker.get_instrument_precision(credentials, instrument)
    purple = algo.Algo(base_interval='15min', slow_interval='30min', aspr_interval='3min', peak_interval='2min')

    # connect to the same Redis DB you used to store the key (default 0)
    r = au.Redis_Utilities(host=REDIS_HOST, port=REDIS_PORT, db=args.db, ttl=ttl)
    prefix_input = f"{PREFIX_INPUT}:{instrument}"
    prefix_output = f"{PREFIX_OUTPUT}:{instrument}"

    r.clear(prefix_output)

    entries = r.read_all(prefix_input)

    for entry in entries:
        print(entry)
        a = process(entry, purple, instrument, precision)
        r.write(prefix_output, a)

    print("waiting for new keys... (Ctrl-C to exit)")
    for entry in r.read_each(prefix_input):
        print(entry)
        a = process(entry, purple, instrument, precision)
        r.write(prefix_output, a)
  

if __name__ == "__main__":
    main()

