"""Reference solution: per-UTC-day traffic report over a stitched access log.

Reads /app/access.log and writes /app/report.json. The log is consolidated from
several web-server and proxy feeds, so the same logical field is serialized more
than one way; the report is defined on the underlying values, so each field is
normalized before it is aggregated:

  * client host   -- an IPv4-mapped IPv6 form (::ffff:A.B.C.D) and a host:port
                     form denote the same host as the bare dotted-quad, so they
                     are folded together before distinct clients are counted.
  * timestamp     -- the calendar day is in UTC, so the logged local time is
                     shifted by its own numeric offset before the date is taken.
  * response size -- a size may be written with thousands separators, which are
                     stripped before the byte total is summed.

Counted requests exclude automated health-check hits to /healthz and collapse
duplicate entries (the same request emitted by more than one feed).
"""

import json
import re
from datetime import datetime, timedelta

LOG_PATH = "/app/access.log"
OUT_PATH = "/app/report.json"
HEALTH = "/healthz"

LINE = re.compile(
    r'^(?P<client>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<path>\S+) [^"]*" (?P<status>\d+) (?P<size>.+?)\s*$'
)

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def canon_host(client):
    if client.startswith("::ffff:"):
        client = client[len("::ffff:"):]
    # a dotted IPv4 with a trailing :port -> drop the port
    if client.count(".") == 3 and ":" in client:
        client = client.split(":", 1)[0]
    return client


def utc_instant(ts):
    body, offset = ts.rsplit(" ", 1)
    day, mon, rest = body.split("/")
    year, hh, mm, ss = re.split("[:]", rest)
    local = datetime(int(year), MONTHS[mon], int(day),
                     int(hh), int(mm), int(ss))
    sign = 1 if offset[0] == "+" else -1
    minutes = sign * (int(offset[1:3]) * 60 + int(offset[3:5]))
    return local - timedelta(minutes=minutes)


def size_bytes(size):
    return int(size.strip().replace(",", ""))


def main():
    seen = set()
    days = {}
    with open(LOG_PATH) as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            m = LINE.match(line)
            if not m:
                continue
            f = m.groupdict()
            if f["path"] == HEALTH:
                continue
            host = canon_host(f["client"])
            instant = utc_instant(f["ts"])
            day = instant.strftime("%Y-%m-%d")
            nbytes = size_bytes(f["size"])
            key = (host, instant, f["method"], f["path"], f["status"], nbytes)
            if key in seen:
                continue
            seen.add(key)
            bucket = days.setdefault(
                day, {"requests": 0, "clients": set(), "bytes": 0})
            bucket["requests"] += 1
            bucket["clients"].add(host)
            bucket["bytes"] += nbytes

    report = {day: {"requests": b["requests"],
                    "clients": len(b["clients"]),
                    "bytes": b["bytes"]}
              for day, b in days.items()}
    with open(OUT_PATH, "w") as out:
        json.dump(report, out, sort_keys=True)


if __name__ == "__main__":
    main()
