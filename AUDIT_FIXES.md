# Audit & Fixes — IoT Protocol Comparison (REST vs GraphQL vs gRPC)

Date: 2026-06-14

## Why the old numbers were illogical

The benchmark code measured the three protocols under **different conditions**,
so the reported latency/RPS numbers were not comparable. Two reports
(`README.md` and `final_report.md`) even disagree with each other (e.g. REST
"160 RPS" vs "544 RPS" for the same Scenario A). Every result table below the
fixes must be **regenerated** — the old figures are invalid.

## Bugs found and fixed

### 1. REST Scenario A only ran at 10 VUs (others ran to 500)
`k6/scenario_a_rest.js` had its 100/500/ramp-down stages commented out, so REST
ingestion was load-tested at **10 VUs for 30s** while GraphQL and gRPC ramped
**10 -> 100 -> 500** over 2 minutes. REST's ingestion numbers were therefore
measured on a fraction of the load.
**Fix:** restored the full `10/100/500/0` stage profile.

### 2. REST Scenario B hit a broken URL (every request 404'd)
`k6/scenario_b_rest.js` requested `…/api/sensork6 -data/selective/M1…` — a typo
with an injected `k6 ` and a space. That path returns 404, so the "selective
read" REST test never touched the real endpoint, yet the report claims 100%
success. The numbers were meaningless.
**Fix:** corrected the URL to `/api/sensor-data/selective/M1?limit=1`.

### 3. gRPC was crippled by the k6 client pattern (the main reason it "looked slow")
All three gRPC scripts:
- opened a **new connection every iteration** and `client.close()`d it,
- ran a hidden **inner loop of 50 serial `invoke`s** with `sleep(0.05)`,
while REST/GraphQL did **one request per iteration** with `sleep(0.1)`.
This is a well-known k6 anti-pattern: per-iteration connect/teardown plus serial
fan-out destroys gRPC throughput and inflates latency. The "gRPC is slow"
conclusion was a measurement artifact, not a property of the protocol.
**Fix:** rewrote all three gRPC scripts to connect **once per VU**
(`if (__ITER === 0) client.connect(...)`), do **one invoke per iteration**, and
`sleep(0.1)` — identical work and think-time to REST/GraphQL.

### 4. Connection-pool asymmetry — the "limited by number of users" bug
This is the one you remembered fixing on gRPC but not finishing:
- gRPC: `ThreadedConnectionPool(1, 500)` + `ThreadPoolExecutor(max_workers=500)`
- REST & GraphQL: `new Pool()` with **no max → node-postgres default of 10**.
Under 100–500 VUs the Node services were throttled to **10 concurrent DB
connections** while gRPC had up to 500, so REST/GraphQL queued and looked slower
purely because of an unequal pool size.
**Fix:** set `max: 500` on both Node pools so all three services have equal DB
concurrency. (Postgres is already started with `max_connections=1000`, so this
is safe.)

### 5. REST aggregate returned numbers as JSON strings (type mismatch)
REST's aggregate query left `AVG(...)`/`COUNT(*)` uncast, so PostgreSQL returned
them as `numeric`/`bigint` → serialized as **strings** (`"total_readings":"123"`),
while GraphQL and gRPC cast to `::float`/`::int` and returned real numbers. Same
query, different typed output.
**Fix:** added `::float` / `::int` casts in `rest/server.js` to match the others.

### 6. Scenario B point-read was ~400x too slow (wrong index chosen)
The selective query `WHERE device_id=? ORDER BY timestamp DESC LIMIT N` ran in
~365 ms because a standalone `(timestamp)` index tempted the planner into
scanning the whole time-ordered table newest-first and filtering by `device_id`
(removing ~694k rows per query). Under 500 VUs this became ~12 s p95. Since every
M-station's data sits in a narrow time window, the time-only index was actively
harmful and unused by any scenario (all three filter by `device_id`).
**Fix:** dropped the standalone time index; kept a single composite
`(device_id, timestamp DESC)` index in `db/init.sql`. Scenario B point-read
dropped to ~0.1 ms and Scenario B became the fastest scenario (as expected).
Also removed accumulated `device-1` ingestion rows so the DB equals `dataset.csv`
(613,392 rows / 9 stations) before measuring.

## What is now guaranteed equal across protocols

- Load profile: `10 → 100 → 500 → 0`, 30s per stage, in all 9 scripts.
- Think-time: a single `sleep(0.1)` per iteration everywhere.
- Work per iteration: exactly one request/invoke (no hidden inner loops).
- Server DB concurrency: pool of 500 for REST, GraphQL and gRPC.
- Aggregate response field types: numeric in all three.

## How to verify (the test)

`validate.py` checks all of the above:

```bash
python validate.py --static    # logic/fairness checks, nothing needs to run
python validate.py             # also runs cross-protocol parity checks if the
                               # docker stack is up (aggregate values agree,
                               # field types correct, payload sizes measured)
```

Static fairness checks pass; runtime parity (REST==GraphQL aggregates, numeric
types, payload sizes) confirmed with the stack up (see `validate_report.txt`).

## Done — benchmarks run and reports updated

1. `docker-compose up --build -d` (or reuse the seeded `pgdata` volume).
2. All 9 k6 scenarios re-run via `python run_tests.py` (one consistent pass,
   100% success), with `docker stats` sampled for peak CPU/RAM.
3. `python validate.py` confirms the fairness conditions hold.
4. Result tables in `README.md`, `final_report.md` and `projekat-iots.docx`
   filled with the fresh, now-comparable numbers; the old contradictory tables
   are gone. Raw evidence is in `results/` (9 `scenario_*.json` + `all.stats`).
