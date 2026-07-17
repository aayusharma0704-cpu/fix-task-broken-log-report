"""Deterministic generator for the stitched-access-log task.

Produces log text plus the ground-truth per-UTC-day report, where the report is
computed from the STRUCTURED truth of each request (canonical client, true UTC
instant, true byte size) BEFORE the request is serialized into a log line. The
serializer then renders each request in one of several feed-specific encodings.
Because the expected report never touches the serialized text, it shares no
decode path with any solver and cannot inherit a decode bug.

Counted requests exclude health-check hits to /healthz and collapse duplicate
log entries (the same request emitted by more than one feed).

Three feed-level serialization divergences are the crux; each is discoverable by
inspecting the data and uniquely decodable, and NONE is stated in the prompt:

  H1  client host: bare IPv4  vs  ::ffff:-mapped IPv6  vs  host:port
  H2  timestamp:   real UTC offset (+0000, +0530, -0700, ...) that can push a
                   request's local calendar date off its true UTC date
  H3  byte size:   plain integer  vs  thousands-grouped integer ("12,345")

In the shipped sample these divergences appear ONLY on non-counted lines
(health-check and duplicate lines), so a parser that ignores them still matches
the sample. In held-out logs they land on counted lines, coupled onto one day.
"""

import random
import re
from datetime import datetime, timedelta, timezone

_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_PATHS = ["/index.html", "/about.html", "/api/login", "/api/items", "/contact",
          "/pricing", "/blog/post-1", "/assets/app.js", "/search", "/cart"]
_METHODS = ["GET", "GET", "GET", "POST", "HEAD"]
_HEALTH = "/healthz"


# --------------------------------------------------------------------------- #
# serialization helpers
# --------------------------------------------------------------------------- #
def _client_field(ip, variant):
    if variant == "bare":
        return ip
    if variant == "mapped":
        return "::ffff:" + ip
    if variant == "port":
        return ip + ":" + str(40000 + (sum(int(o) for o in ip.split(".")) % 20000))
    raise ValueError(variant)


def _size_field(nbytes, variant):
    if variant == "plain":
        return str(nbytes)
    if variant == "grouped":
        return format(nbytes, ",")
    raise ValueError(variant)


def _ts_field(utc_dt, offset_min):
    """Render the local wall-clock time for the given UTC instant + offset."""
    local = utc_dt + timedelta(minutes=offset_min)
    sign = "+" if offset_min >= 0 else "-"
    a = abs(offset_min)
    off = "%s%02d%02d" % (sign, a // 60, a % 60)
    return "%02d/%s/%04d:%02d:%02d:%02d %s" % (
        local.day, _MON[local.month - 1], local.year,
        local.hour, local.minute, local.second, off)


def _line(ip, variant_ip, utc_dt, offset_min, method, path, status, nbytes,
          variant_size):
    return '%s - - [%s] "%s %s HTTP/1.1" %d %s' % (
        _client_field(ip, variant_ip),
        _ts_field(utc_dt, offset_min),
        method, path, status,
        _size_field(nbytes, variant_size),
    )


# --------------------------------------------------------------------------- #
# a request record carries its STRUCTURED truth
# --------------------------------------------------------------------------- #
class Req:
    __slots__ = ("ip", "utc", "method", "path", "status", "nbytes",
                 "v_ip", "v_size", "offset", "dup")

    def __init__(self, ip, utc, method, path, status, nbytes,
                 v_ip="bare", v_size="plain", offset=0, dup=False):
        self.ip = ip
        self.utc = utc
        self.method = method
        self.path = path
        self.status = status
        self.nbytes = nbytes
        self.v_ip = v_ip
        self.v_size = v_size
        self.offset = offset
        self.dup = dup

    def counted(self):
        return self.path != _HEALTH

    def render(self):
        return _line(self.ip, self.v_ip, self.utc, self.offset,
                     self.method, self.path, self.status, self.nbytes,
                     self.v_size)


def _expected(reqs):
    """Ground-truth report from structured truth: unique counted requests only."""
    seen = set()
    days = {}
    for r in reqs:
        if not r.counted():
            continue
        key = (r.ip, r.utc, r.method, r.path, r.status, r.nbytes)
        if key in seen:          # same request from another feed -> count once
            continue
        seen.add(key)
        day = r.utc.strftime("%Y-%m-%d")
        d = days.setdefault(day, {"requests": 0, "clients": set(), "bytes": 0})
        d["requests"] += 1
        d["clients"].add(r.ip)
        d["bytes"] += r.nbytes
    return {day: {"requests": v["requests"],
                  "clients": len(v["clients"]),
                  "bytes": v["bytes"]}
            for day, v in days.items()}


def _render_all(reqs, rng):
    lines = []
    for r in reqs:
        lines.append(r.render())
        if r.dup:                       # byte-identical second-feed copy
            lines.append(r.render())
    rng.shuffle(lines)
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# sample: anomalies ONLY on non-counted (health-check / duplicate) lines
# --------------------------------------------------------------------------- #
def make_sample():
    Z = timezone.utc
    reqs = []

    def u(y, mo, d, h, mi, s=0):
        return datetime(y, mo, d, h, mi, s, tzinfo=Z)

    # ---- counted traffic, all uniform: bare IPv4, +0000, plain bytes ----
    counted = [
        ("203.0.113.10", u(2026, 6, 15, 9, 0), "GET", "/index.html", 200, 1024),
        ("203.0.113.11", u(2026, 6, 15, 9, 5), "GET", "/about.html", 200, 512),
        ("203.0.113.10", u(2026, 6, 15, 9, 6), "GET", "/pricing", 200, 800),
        ("203.0.113.12", u(2026, 6, 15, 10, 0), "POST", "/api/login", 401, 64),
        ("203.0.113.12", u(2026, 6, 15, 10, 1), "GET", "/api/items", 200, 2048),
        ("203.0.113.13", u(2026, 6, 16, 8, 0), "GET", "/index.html", 200, 1024),
        ("203.0.113.11", u(2026, 6, 16, 8, 30), "GET", "/blog/post-1", 200, 4096),
        ("203.0.113.14", u(2026, 6, 16, 12, 0), "GET", "/assets/app.js", 200, 900),
        ("203.0.113.13", u(2026, 6, 16, 12, 5), "GET", "/contact", 200, 300),
        ("203.0.113.15", u(2026, 6, 16, 18, 0), "HEAD", "/index.html", 200, 0),
    ]
    for ip, utc, m, p, st, nb in counted:
        reqs.append(Req(ip, utc, m, p, st, nb))

    # one legitimate duplicate of a counted request (identical second feed)
    reqs.append(Req("203.0.113.10", u(2026, 6, 15, 9, 0), "GET",
                    "/index.html", 200, 1024, dup=True))

    # ---- health-check lines (EXCLUDED) carry every anomalous encoding ----
    reqs.append(Req("203.0.113.90", u(2026, 6, 15, 9, 30), "GET", _HEALTH, 200,
                    12345, v_ip="mapped", v_size="grouped"))
    reqs.append(Req("203.0.113.91", u(2026, 6, 15, 23, 50), "GET", _HEALTH, 200,
                    2048, v_ip="port", offset=330))      # +0530
    reqs.append(Req("203.0.113.92", u(2026, 6, 16, 1, 0), "GET", _HEALTH, 200,
                    64, offset=-420))                     # -0700

    rng = random.Random(0)
    return _render_all(reqs, rng), _expected(reqs)


# --------------------------------------------------------------------------- #
# held-out: anomalies forced onto COUNTED lines, coupled onto one target day
# --------------------------------------------------------------------------- #
def make_export(seed):
    rng = random.Random(1000 + seed)
    Z = timezone.utc
    reqs = []

    base_day = 15 + (seed % 3)                    # 15,16,17 June
    target = datetime(2026, 6, base_day, tzinfo=Z)
    prev = target - timedelta(days=1)
    nxt = target + timedelta(days=1)

    def ip(n):
        return "198.51.100.%d" % n

    # ---------- background counted traffic on 3 days, all uniform ----------
    def bg(day_dt, count, start_ip):
        for i in range(count):
            hh = rng.randint(6, 20)
            mm = rng.randint(0, 59)
            utc = day_dt.replace(hour=hh, minute=mm,
                                 second=rng.randint(0, 59))
            reqs.append(Req(ip(start_ip + (i % 6)), utc,
                            rng.choice(_METHODS),
                            rng.choice(_PATHS),
                            rng.choice([200, 200, 200, 404, 500]),
                            rng.choice([256, 512, 800, 1024, 3000])))

    bg(prev, 12, 10)
    bg(target, 10, 20)
    bg(nxt, 12, 40)

    # ---------- H1: same host as bare AND mapped AND port on target day ----
    host = ip(70)
    reqs.append(Req(host, target.replace(hour=9, minute=1), "GET",
                    "/index.html", 200, 1024, v_ip="bare"))
    reqs.append(Req(host, target.replace(hour=9, minute=2), "GET",
                    "/api/items", 200, 512, v_ip="mapped"))
    reqs.append(Req(host, target.replace(hour=9, minute=3), "GET",
                    "/pricing", 200, 800, v_ip="port"))
    # a second host appears bare on target and mapped on target
    host2 = ip(71)
    reqs.append(Req(host2, target.replace(hour=14, minute=0), "GET",
                    "/cart", 200, 640, v_ip="bare"))
    reqs.append(Req(host2, target.replace(hour=14, minute=5), "GET",
                    "/search", 200, 720, v_ip="mapped"))

    # ---------- H2: true UTC on target day, local date lands on a neighbour #
    #  early-morning UTC with negative offset -> local shows PREVIOUS day
    reqs.append(Req(ip(80), target.replace(hour=1, minute=10), "GET",
                    "/index.html", 200, 1500, offset=-420))     # -0700
    #  late-night UTC with positive offset -> local shows NEXT day
    reqs.append(Req(ip(81), target.replace(hour=22, minute=50), "GET",
                    "/blog/post-1", 200, 1700, offset=330))     # +0530
    #  and a decoy on a neighbour day whose local lands ON target (must NOT
    #  be counted into target): true prev-day late-night, +0530 -> local target
    reqs.append(Req(ip(82), prev.replace(hour=22, minute=40), "GET",
                    "/contact", 200, 250, offset=330))

    # ---------- H3: grouped byte sizes on counted target-day lines ----------
    reqs.append(Req(ip(83), target.replace(hour=11, minute=0), "GET",
                    "/assets/app.js", 200, 12345, v_size="grouped"))
    reqs.append(Req(ip(84), target.replace(hour=11, minute=30), "GET",
                    "/api/items", 200, 45678, v_size="grouped"))

    # ---------- disclosed free hazards: dup + health-check ----------
    reqs.append(Req(ip(85), target.replace(hour=8, minute=0), "GET",
                    "/index.html", 200, 1024, dup=True))       # identical dup
    reqs.append(Req(ip(99), target.replace(hour=8, minute=1), "GET",
                    _HEALTH, 200, 33333, v_ip="mapped", v_size="grouped"))
    reqs.append(Req(ip(98), nxt.replace(hour=3, minute=0), "GET",
                    _HEALTH, 200, 40000, offset=330))

    log = _render_all(reqs, rng)
    exp = _expected(reqs)
    _check_export(log, exp, target)
    return log, exp


# --------------------------------------------------------------------------- #
# build-time fairness assertions
# --------------------------------------------------------------------------- #
def _check_export(log, exp, target):
    tkey = target.strftime("%Y-%m-%d")
    assert len(exp) >= 2, "need multiple days"
    assert tkey in exp, "target day missing from expected"
    assert "::ffff:" in log, "no mapped-IPv6 client present"
    assert any(":" in ln.split(" ")[0] and "ffff" not in ln.split(" ")[0]
               for ln in log.splitlines()), "no host:port client present"
    assert "+0530" in log or "-0700" in log, "no non-UTC offset present"
    # a grouped size on a COUNTED (non-health) line
    grouped_counted = [ln for ln in log.splitlines()
                       if "," in ln.split('"')[-1] and _HEALTH not in ln]
    assert grouped_counted, "no grouped byte size on a counted line"
    assert _HEALTH in log, "no health-check line present"
    # naive default must be WRONG on this export
    assert naive_report(log) != exp, "naive parser accidentally correct"


# --------------------------------------------------------------------------- #
# reference wrong-default and partial fixes (calibration only; not shipped)
# --------------------------------------------------------------------------- #
_LINE_RE = re.compile(
    r'^(?P<client>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<method>\S+) '
    r'(?P<path>\S+) [^"]*" (?P<status>\d+) (?P<size>.+)$')


def _parse(log):
    rows = []
    for ln in log.splitlines():
        m = _LINE_RE.match(ln)
        if m:
            rows.append(m.groupdict())
    return rows


def _agg(records):
    """records: list of (client, day, nbytes); already counted+deduped."""
    days = {}
    for client, day, nb in records:
        d = days.setdefault(day, {"requests": 0, "clients": set(), "bytes": 0})
        d["requests"] += 1
        d["clients"].add(client)
        d["bytes"] += nb
    return {day: {"requests": v["requests"], "clients": len(v["clients"]),
                  "bytes": v["bytes"]} for day, v in days.items()}


def _canon_ip(c):
    if c.startswith("::ffff:"):
        c = c[len("::ffff:"):]
    # strip :port from dotted IPv4
    if c.count(".") == 3 and ":" in c:
        c = c.split(":")[0]
    return c


def _utc_day(ts):
    # ts like "16/Jun/2026:22:50:00 +0530"
    body, off = ts.rsplit(" ", 1)
    dt = datetime.strptime(body, "%d/%b/%Y:%H:%M:%S")
    sign = 1 if off[0] == "+" else -1
    mins = sign * (int(off[1:3]) * 60 + int(off[3:5]))
    dt = dt - timedelta(minutes=mins)
    return dt.strftime("%Y-%m-%d")


def _local_day(ts):
    body, _off = ts.rsplit(" ", 1)
    dt = datetime.strptime(body, "%d/%b/%Y:%H:%M:%S")
    return dt.strftime("%Y-%m-%d")


def _size_plain(s):
    s = s.strip()
    return int(s) if s.isdigit() else 0


def _size_grouped(s):
    return int(s.strip().replace(",", ""))


def _dedup(rows):
    seen, out = set(), []
    for r in rows:
        key = (r["client"], r["ts"], r["method"], r["path"], r["status"],
               r["size"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _report(log, fix_ip, fix_day, fix_size):
    rows = _dedup(_parse(log))
    recs = []
    for r in rows:
        if r["path"] == _HEALTH:
            continue
        client = _canon_ip(r["client"]) if fix_ip else r["client"]
        day = _utc_day(r["ts"]) if fix_day else _local_day(r["ts"])
        nb = _size_grouped(r["size"]) if fix_size else _size_plain(r["size"])
        recs.append((client, day, nb))
    return _agg(recs)


def naive_report(log):
    return _report(log, False, False, False)


def correct_report(log):
    return _report(log, True, True, True)


def partial_variants(log):
    return {
        "fix_ip_only": _report(log, True, False, False),
        "fix_day_only": _report(log, False, True, False),
        "fix_size_only": _report(log, False, False, True),
        "miss_ip": _report(log, False, True, True),
        "miss_day": _report(log, True, False, True),
        "miss_size": _report(log, True, True, False),
    }
