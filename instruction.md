There is a web access log at `/app/access.log`. It has been consolidated from
several different web-server and proxy feeds, so entries do not all follow an
identical convention. Write a program at `/app/process_log.py` that reads
`/app/access.log` and writes a traffic report to `/app/report.json`. Your
program will be executed as `python3 /app/process_log.py`.

The report groups counted requests by the UTC calendar day on which they
occurred. `/app/report.json` must be a JSON object whose keys are days written
as `YYYY-MM-DD` strings. Each day maps to an object with exactly these keys:

- `requests` — the number of counted requests on that day.
- `clients` — the number of distinct client hosts that made counted requests on
  that day.
- `bytes` — the total number of response bytes served for counted requests on
  that day.

A request is counted unless it is an automated health check to the path
`/healthz`, which is never counted. The same request is sometimes recorded by
more than one feed; it must be counted only once.

Notes:
- The day is the UTC calendar day of the request. A client host is identified by
  the machine that made the request. Response bytes are the number of bytes in
  the response.
- Include every day that has at least one counted request, and only those days.
  All three values are exact non-negative integers.
- The same program will be run unchanged against other logs exported from this
  same platform, so it must be correct in general rather than tuned to the
  entries in the shipped file.

Write only `/app/report.json` and `/app/process_log.py`.
