There is an access log at `/app/access.log` in the working directory. Analyze the
traffic and produce a summary report.

Save your findings as a JSON file at `/app/report.json` with exactly these keys:

1. `total_requests` — the total number of requests in the log.
2. `unique_ips` — the number of distinct client IP addresses.
3. `top_path` — the most frequently requested path.