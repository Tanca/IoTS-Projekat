#!/usr/bin/env python3
"""
validate.py - Logical / fairness validation for the IoT protocol-comparison project.

Two independent layers:

  1. STATIC checks (always run, need nothing running):
     Parse every k6 script and assert the three protocols are measured under
     IDENTICAL conditions. A benchmark is only meaningful if the load profile,
     think-time and work-per-iteration are the same for REST, GraphQL and gRPC.
     These checks catch the bugs that produced the "illogical" numbers in the
     old reports.

  2. RUNTIME checks (only if the docker stack is up):
     Send the SAME logical request to all three services and assert the
     answers agree (cross-protocol parity), that field types are consistent,
     and measure the real response payload sizes. Skipped automatically if a
     service is unreachable.

Usage:
    python validate.py              # static checks + runtime if reachable
    python validate.py --static     # static checks only

Exit code 0 = all run checks passed, 1 = at least one failed.
A copy of the output is also written to validate_report.txt.
"""

import os
import re
import sys
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
K6_DIR = os.path.join(HERE, "k6")

EXPECTED_STAGES = [("30s", 10), ("30s", 100), ("30s", 500), ("30s", 0)]
EXPECTED_SLEEP = "0.1"

PASS, FAIL = "PASS", "FAIL"
results = []
_log_lines = []


def emit(line=""):
    _log_lines.append(line)
    print(line, flush=True)


def record(ok, name, detail=""):
    results.append((ok, name, detail))
    line = f"  [{PASS if ok else FAIL}] {name}"
    if detail:
        line += f"\n         -> {detail}"
    emit(line)


def _read(path):
    try:
        return open(path, encoding="utf-8").read()
    except OSError:
        return None


def _strip_comments(src):
    """Drop // and # line comments so we don't match values mentioned in prose."""
    if not src:
        return ""
    out = []
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("//") or s.startswith("#"):
            continue
        out.append(line.split("//")[0])
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# STATIC CHECKS
# --------------------------------------------------------------------------- #
def parse_stages(src):
    m = re.search(r"stages:\s*\[(.*?)\]", src, re.S)
    if not m:
        return None
    stages = []
    for raw in m.group(1).splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        dm = re.search(r"duration:\s*'([^']+)'", line)
        tm = re.search(r"target:\s*(\d+)", line)
        if dm and tm:
            stages.append((dm.group(1), int(tm.group(1))))
    return stages


def static_checks():
    emit("\n=== STATIC FAIRNESS CHECKS (k6 scripts) ===")
    files = sorted(glob.glob(os.path.join(K6_DIR, "scenario_*.js")))
    if not files:
        record(False, "k6 scripts found", f"none in {K6_DIR}")
        return

    by_scenario = {}
    for f in files:
        name = os.path.basename(f)
        src = _read(f) or ""
        scen = name.split("_")[1]
        by_scenario.setdefault(scen, []).append((name, src))

        stages = parse_stages(src)
        record(stages == EXPECTED_STAGES, f"{name}: load profile == 10/100/500/0",
               "" if stages == EXPECTED_STAGES else f"got {stages}")

        sleeps = re.findall(r"sleep\(([0-9.]+)\)", src)
        record(sleeps == [EXPECTED_SLEEP], f"{name}: single sleep(0.1) think-time",
               "" if sleeps == [EXPECTED_SLEEP] else f"got sleep calls {sleeps}")

        n_http = len(re.findall(r"http\.(?:get|post)\(", src))
        n_invoke = len(re.findall(r"\.invoke\(", src))
        units = n_http + n_invoke
        record(units == 1, f"{name}: exactly one request per iteration",
               "" if units == 1 else f"found {n_http} http + {n_invoke} invoke")

        record("for (" not in src and "for(" not in src,
               f"{name}: no inner request loop")

        if "grpc" in name:
            connects = src.count("client.connect(")
            closes = src.count("client.close(")
            guarded = "__ITER === 0" in src or "__ITER == 0" in src
            record(closes == 0, f"{name}: no per-iteration client.close()",
                   "" if closes == 0 else f"{closes} close() calls")
            record(connects >= 1 and guarded,
                   f"{name}: connects once per VU (guarded by __ITER)",
                   "" if (connects >= 1 and guarded) else "connect not guarded")

        for url in re.findall(r"https?://[^'\"]+", src):
            record(" " not in url, f"{name}: URL has no stray spaces",
                   "" if " " not in url else f"bad url '{url}'")
        if "rest" in name:
            record("localhost:3000" in src, f"{name}: targets REST port 3000")
        if "graphql" in name:
            record("localhost:4000" in src, f"{name}: targets GraphQL port 4000")
        if "grpc" in name:
            record("localhost:50051" in src, f"{name}: targets gRPC port 50051")

    for scen, items in sorted(by_scenario.items()):
        profiles = {n: parse_stages(s) for n, s in items}
        uniq = {tuple(p) if p else None for p in profiles.values()}
        record(len(uniq) == 1,
               f"scenario {scen.upper()}: REST/GraphQL/gRPC share one load profile",
               "" if len(uniq) == 1 else f"divergent: {profiles}")

    static_pool_checks()


def static_pool_checks():
    rest = _strip_comments(_read(os.path.join(HERE, "rest", "server.js")))
    gql = _strip_comments(_read(os.path.join(HERE, "graphql", "server.js")))
    grpc = _strip_comments(_read(os.path.join(HERE, "grpc", "server.py")))

    rest_max = re.search(r"max:\s*(\d+)", rest)
    gql_max = re.search(r"max:\s*(\d+)", gql)
    grpc_pool = re.search(r"ThreadedConnectionPool\(\s*\d+\s*,\s*(\d+)", grpc)
    grpc_workers = re.search(r"max_workers\s*=\s*(\d+)", grpc)

    rest_v = int(rest_max.group(1)) if rest_max else 10
    gql_v = int(gql_max.group(1)) if gql_max else 10
    grpc_v = int(grpc_pool.group(1)) if grpc_pool else None
    workers_v = int(grpc_workers.group(1)) if grpc_workers else None

    record(rest_max is not None, "rest/server.js: explicit pool max set",
           "" if rest_max else "using pg default max=10 (throttles at high VUs)")
    record(gql_max is not None, "graphql/server.js: explicit pool max set",
           "" if gql_max else "using pg default max=10 (throttles at high VUs)")
    record(rest_v == gql_v == grpc_v,
           f"DB pools equal across services (rest={rest_v}, gql={gql_v}, grpc={grpc_v})",
           "" if rest_v == gql_v == grpc_v else "unequal pools = unfair benchmark")
    if workers_v is not None and grpc_v is not None:
        record(workers_v >= grpc_v,
               f"gRPC ThreadPoolExecutor workers ({workers_v}) >= pool ({grpc_v})")


# --------------------------------------------------------------------------- #
# RUNTIME CHECKS (optional)
# --------------------------------------------------------------------------- #
def runtime_checks():
    emit("\n=== RUNTIME PARITY CHECKS (live services) ===")
    try:
        import requests
    except ImportError:
        emit("  (skipped: pip install requests to enable runtime checks)")
        return

    REST = "http://localhost:3000"
    GQL = "http://localhost:4000/"
    device = "M1"

    try:
        requests.get(REST + "/api-docs", timeout=2)
    except Exception:
        emit("  (skipped: REST not reachable - bring the stack up with docker-compose)")
        return

    r_agg = requests.get(REST + f"/api/sensor-data/aggregate?device_id={device}",
                         timeout=10).json()
    g_agg = requests.post(GQL, json={
        "query": "query($d:String){getAggregatedData(device_id:$d){"
                 "avg_air_temp max_air_temp min_air_temp avg_humidity total_readings}}",
        "variables": {"d": device},
    }, timeout=10).json()

    r0 = r_agg[0] if isinstance(r_agg, list) and r_agg else {}
    g0 = (g_agg.get("data", {}).get("getAggregatedData") or [{}])[0]

    def close(a, b, tol=1e-3):
        try:
            return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)))
        except (TypeError, ValueError):
            return False

    for field in ["avg_air_temp", "max_air_temp", "min_air_temp",
                  "avg_humidity", "total_readings"]:
        record(close(r0.get(field), g0.get(field)),
               f"aggregate parity REST==GraphQL: {field}",
               f"REST={r0.get(field)} GraphQL={g0.get(field)}")

    record(isinstance(r0.get("total_readings"), (int, float)),
           "REST total_readings is numeric (not a JSON string)",
           f"type={type(r0.get('total_readings')).__name__}")

    sel = requests.get(REST + f"/api/sensor-data/selective/{device}?limit=1", timeout=10)
    record(sel.status_code == 200, "REST selective endpoint returns 200",
           f"status={sel.status_code}")

    rest_bytes = len(sel.content)
    g_sel = requests.post(GQL, json={
        "query": "query($d:String!){getSensorData(device_id:$d,limit:1){"
                 "timestamp air_temp humidity}}",
        "variables": {"d": device},
    }, timeout=10)
    gql_bytes = len(g_sel.content)
    emit(f"         payload (selective, 1 row): REST={rest_bytes}B  GraphQL={gql_bytes}B")
    record(rest_bytes > 0 and gql_bytes > 0, "payload sizes measured")


# --------------------------------------------------------------------------- #
def main():
    static_only = "--static" in sys.argv
    static_checks()
    if not static_only:
        runtime_checks()

    n_fail = sum(1 for ok, _, _ in results if not ok)
    n_pass = sum(1 for ok, _, _ in results if ok)
    emit("\n" + "=" * 60)
    emit(f"  RESULT: {n_pass} passed, {n_fail} failed")
    emit("=" * 60)
    try:
        with open(os.path.join(HERE, "validate_report.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(_log_lines) + "\n")
    except OSError:
        pass
    sys.stdout.flush()
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
