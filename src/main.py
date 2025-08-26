"""Main entry point for streaming price data from Redis and processing with
TimeBasedStreamingMA.

This script supports two delivery formats commonly seen in Redis:

- Redis Streams: a single stream key like "price_data:USD_CAD" with stream
  entries holding fields (one field can contain the JSON string under some
  field name such as "string").
- Per-message keys: individual keys named like "price_data:WTICO_USD:<id>"
  with the JSON payload stored as a Redis string value.

The listener auto-detects which format is present for the requested
instrument and falls back to the per-key scan mode if no stream key exists.
Processed per-message keys are deleted to avoid re-processing.
"""

import argparse
import json
import time
from typing import Optional

import redis

from algo import TimeBasedStreamingMA


REDIS_HOST = "localhost"
REDIS_PORT = 6379
STREAM_PREFIX = "prices:"
SIGNALS_STREAM = "signals"


def _extract_price_payload_from_stream_fields(fields: dict) -> Optional[dict]:
    """Try to extract a JSON payload from Redis stream fields.

    Many producers place the whole JSON string under a single field (e.g.
    'string'). Other producers may add individual fields (timestamp, price,...)
    -- in that case we convert the field dict into a payload dict.
    """
    if not fields:
        return None

    # If any field value looks like JSON, prefer it
    for v in fields.values():
        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
            try:
                return json.loads(v)
            except Exception:
                pass

    # Otherwise, assume fields are the payload already (timestamp, price, ...)
    # Convert numeric strings to numbers where possible
    payload = {}
    for k, v in fields.items():
        try:
            payload[k] = json.loads(v) if isinstance(v, str) and (v.startswith("[") or v.startswith("{")) else v
        except Exception:
            payload[k] = v
    return payload


def process_price_payload(payload: dict, instrument: str, ma: TimeBasedStreamingMA, r: Optional[redis.Redis] = None, signals_stream: str = SIGNALS_STREAM, ttl: Optional[int] = None):
    if not payload:
        return None
    # Normalize keys
    timestamp = payload.get("timestamp") or payload.get("time")
    price = payload.get("price") or payload.get("mid") or payload.get("last")
    if price is None:
        # try to infer from bid/ask
        bid = payload.get("bid")
        ask = payload.get("ask")
        if bid is not None and ask is not None:
            try:
                price = (float(bid) + float(ask)) / 2.0
            except Exception:
                price = None

    if price is None:
        return None

    ma_value = ma.add_data_point(timestamp, float(price))
    print(f"{timestamp} {instrument} price={price} MA={ma_value}")

    # Write result to Redis string keys (signals) if redis client provided.
    if r is not None:
        entry = {
            "instrument": instrument,
            "timestamp": str(timestamp),
            "price": str(price),
            # store MA as JSON so complex objects are supported
            "ma": ma_value if isinstance(ma_value, (str, int, float)) else ma_value
        }

        # Per-suffix or per-instrument key provided in signals_stream
        try:
            if ttl:
                r.set(signals_stream, json.dumps(entry), ex=int(ttl))
            else:
                r.set(signals_stream, json.dumps(entry))
        except Exception as exc:
            print(f"Failed to SET {signals_stream}: {exc}")

        # Also write a consolidated per-instrument key: signals:<instrument>
        try:
            consolidated = f"signals:{instrument}"
            if ttl:
                r.set(consolidated, json.dumps(entry), ex=int(ttl))
            else:
                r.set(consolidated, json.dumps(entry))
        except Exception as exc:
            print(f"Failed to SET consolidated {consolidated}: {exc}")

    return ma_value

def listen(instrument: str, ma_window: str = "5min", ma_type: str = "SMA", ttl: Optional[int] = None):
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    stream_key = f"{STREAM_PREFIX}{instrument}"
    ma = TimeBasedStreamingMA(ma_window, ma_type)

    # Detect if stream_key exists and is a Redis stream
    try:
        key_type = r.type(stream_key)
    except Exception:
        key_type = None

    print(f"Listening for instrument={instrument} (stream key: {stream_key})")

    if key_type == "stream":
        print("Detected Redis stream. Using XREAD to consume entries.")
        last_id = "0-0"
        try:
            while True:
                messages = r.xread({stream_key: last_id}, block=1000, count=10)
                if not messages:
                    continue
                for stream, entries in messages:
                    for entry_id, fields in entries:
                        last_id = entry_id
                        payload = _extract_price_payload_from_stream_fields(fields)
                        # Use a per-instrument signals stream for stream-mode
                        signals_stream = f"signals:{instrument}"
                        process_price_payload(payload, instrument, ma, r=r, signals_stream=signals_stream, ttl=ttl)
        except KeyboardInterrupt:
            print("Interrupted, exiting stream listener")
            return

    else:
        # Fallback: many setups push discrete keys like price_data:INSTRUMENT:<id>
        print("Stream key not found or not a stream; falling back to per-key scan mode.")
        pattern = f"{STREAM_PREFIX}{instrument}:*"
        try:
            while True:
                seen_any = False
                for key in r.scan_iter(match=pattern, count=100):
                    seen_any = True
                    try:
                        value = r.get(key)
                        if not value:
                            r.delete(key)
                            continue
                        payload = None
                        try:
                            payload = json.loads(value)
                        except Exception:
                            # If it's not JSON, skip
                            payload = None
                        # derive suffix from key if possible: price_data:<instrument>:<suffix>
                        parts = key.split(":")
                        if len(parts) >= 3:
                            suffix = parts[2]
                            signals_stream = f"signals:{instrument}:{suffix}"
                        else:
                            signals_stream = f"signals:{instrument}"

                        process_price_payload(payload, instrument, ma, r=r, signals_stream=signals_stream, ttl=ttl)
                    finally:
                        # delete processed key to avoid re-processing
                        try:
                            r.delete(key)
                        except Exception:
                            pass

                # If nothing was found, sleep briefly before scanning again
                if not seen_any:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            print("Interrupted, exiting key-scan listener")
            return


def main():
    parser = argparse.ArgumentParser(
        description="Listen to Redis price stream or per-key price messages and process with TimeBasedStreamingMA."
    )
    parser.add_argument("--instrument", type=str, default="USD_CAD", help="Instrument to listen to (e.g. USD_CAD)")
    parser.add_argument("--ma_window", type=str, default="15min", help="Moving average window (e.g. 5min, 1H)")
    parser.add_argument("--ma_type", type=str, default="EMA", help="Type of moving average (SMA, EMA, DEMA, TEMA)")
    parser.add_argument("--ttl", type=int, default=None, help="TTL in seconds for signals keys (optional)")
    args = parser.parse_args()
    listen(args.instrument, args.ma_window, args.ma_type, ttl=args.ttl)


if __name__ == "__main__":
    main()
