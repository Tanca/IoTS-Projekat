#!/usr/bin/env python3
"""
run_tests.py - pokrece sve k6 load testove jedan po jedan.

Vazno za screenshot-ove: ova skripta NE sakriva k6 izlaz. k6 svoj zavrsni
izvestaj (RPS, http_req_duration/grpc_req_duration, p95, checks) ispisuje u
terminal na kraju svakog testa, pa svaki summary mozes da screenshot-ujes
uzivo. Pored toga, masinski citljiv summary se cuva u results/<ime>.json
preko k6 opcije --summary-export.

Uslov: instaliran k6 (https://k6.io) i pokrenut sistem:
    docker-compose up --build -d

Pokretanje:
    python run_tests.py            # svi scenariji, svi protokoli
    python run_tests.py a          # samo Scenario A (sva tri protokola)
    python run_tests.py rest       # samo REST (sva tri scenarija)
    python run_tests.py b grpc     # samo Scenario B, gRPC

Napomena: gRPC testovi se pokrecu iz k6/ direktorijuma jer .proto putanja
u skriptama je relativna (../grpc).
"""

import os
import sys
import time
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
K6_DIR = os.path.join(HERE, "k6")
RESULTS = os.path.join(HERE, "results")

SCENARIOS = ["a", "b", "c"]
PROTOCOLS = ["rest", "graphql", "grpc"]


def banner(text):
    line = "=" * 70
    print("\n" + line)
    print("  " + text)
    print(line, flush=True)


def main():
    if shutil.which("k6") is None:
        print("GRESKA: k6 nije pronadjen u PATH-u. Instaliraj k6 pa probaj ponovo.")
        print("Uputstvo: https://k6.io/docs/get-started/installation/")
        sys.exit(1)

    args = [a.lower() for a in sys.argv[1:]]
    scen_filter = [a for a in args if a in SCENARIOS] or SCENARIOS
    proto_filter = [a for a in args if a in PROTOCOLS] or PROTOCOLS

    os.makedirs(RESULTS, exist_ok=True)

    plan = []
    for s in scen_filter:
        for p in proto_filter:
            fname = f"scenario_{s}_{p}.js"
            if os.path.exists(os.path.join(K6_DIR, fname)):
                plan.append((s, p, fname))

    if not plan:
        print("Nema testova za zadati filter.")
        sys.exit(1)

    print(f"Pokrecem {len(plan)} test(ova). Svaki traje ~2 min.")
    print("Screenshot-uj svaki zavrsni k6 summary kako se pojavi na ekranu.")

    failures = []
    for i, (s, p, fname) in enumerate(plan, 1):
        export = os.path.join(RESULTS, f"scenario_{s}_{p}.json")
        banner(f"[{i}/{len(plan)}] Scenario {s.upper()} - {p.upper()}  ({fname})")
        # stdout/stderr se NE hvataju -> k6 summary ide pravo u terminal (za screenshot).
        rc = subprocess.run(
            ["k6", "run", "--summary-export", export, fname],
            cwd=K6_DIR,
        ).returncode
        if rc != 0:
            failures.append(fname)
            print(f"  UPOZORENJE: k6 je vratio kod {rc} za {fname}")
        time.sleep(2)  # mali predah izmedju testova

    banner("ZAVRSENO")
    print(f"JSON summary fajlovi su u: {RESULTS}")
    if failures:
        print("Testovi sa nenultim izlaznim kodom:")
        for f in failures:
            print("  - " + f)
    else:
        print("Svi testovi su prosli bez greske na nivou procesa.")


if __name__ == "__main__":
    main()
