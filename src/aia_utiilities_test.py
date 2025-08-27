
import json
import redis
import time
import uuid
from datetime import datetime

class Redis_Utilities:

    def __init__(self, host='localhost', port=6379, db=0, ttl=120):
        self.host = host
        self.port = port
        self.db = db
        self.ttl = ttl
        self.redis_db = redis.Redis(host=self.host, port=self.port, db=self.db)

    def read_all(self, prefix, order=True):

        # read existing keys and track seen ones
        seen = set()
        items = []
        for key in self.redis_db.scan_iter(f"{prefix}"):
            seen.add(key)
            # print(f"found key={key!r}")
            raw = self.redis_db.get(key)
            # Convert raw JSON to dict
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f" JSON decode error for key={key}: {e}")
            
            items.append(data)

        # Sort items based on timestamp in the dict
        items.sort(key=lambda x: x["timestamp"])
        # print(items)

        return items

    def read_each(self, prefix):
        seen = set()
        while True:
            time.sleep(0.1)
            for key in self.redis_db.scan_iter(f"{prefix}"):
                if key not in seen:
                    seen.add(key)
                    raw = self.redis_db.get(key)
                    try:
                        data = json.loads(raw)
                        yield data  # Send each new entry back to caller
                    except json.JSONDecodeError as e:
                        print(f"JSON decode error for key={key}: {e}")
                        continue


    def write(self, prefix, value):
        assert isinstance(value, dict)
        self.redis_db.set(f"{prefix}:{uuid.uuid4().hex[:8]}", json.dumps(value), ex=self.ttl)



def string_to_datetime(date_string):
    """Convert a string to a datetime object.

    Args:
        date_string (str): The date string to convert.

    Returns:
        datetime: The converted datetime object or None on error.
    """
    try:
        return datetime.fromisoformat(date_string.replace('Z', '+00:00'))
    except Exception as e:
        print(f"Error converting string to datetime: {e}")
        return None

def datetime_to_string(dt):
    """Convert a datetime object to an ISO-8601 string.

    Args:
        dt (datetime): The datetime object to convert.

    Returns:
        str: The converted ISO-8601 string or None on error.
    """
    try:
        return dt.isoformat()
    except Exception as e:
        print(f"Error converting datetime to string: {e}")
        return None