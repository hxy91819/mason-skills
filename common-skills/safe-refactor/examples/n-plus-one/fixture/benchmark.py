"""Count real SQLite SELECTs; this is not a production latency benchmark."""
import argparse
import json
import math
from src.api import list_users
from src.store import Store

p = argparse.ArgumentParser()
p.add_argument("--require-batch", action="store_true")
a = p.parse_args()
results = []
for n in (0, 1, 10, 100, 205):
    store = Store([(i, "A", "user-" + str(i)) for i in range(n)])
    try:
        rows = list_users(store, "A", list(range(n)))
        assert len(rows) == n
        results.append({"rows": n, "sqlite_selects": store.selects})
        if a.require_batch:
            assert store.selects <= math.ceil(n / 100), results[-1]
    finally:
        store.close()
print(json.dumps({"measurement": "real in-memory SQLite SELECT count, not service latency", "results": results}, indent=2))
