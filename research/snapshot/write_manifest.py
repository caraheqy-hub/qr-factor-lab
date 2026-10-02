"""Record immutable file hashes and coverage for the local BaoStock snapshot."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

root = Path(__file__).resolve().parents[2]
files = {
    "members": root / "data/bao_hs300_monthly_members.csv",
    "bars": root / "data/bao_hs300_2019_2026.csv",
    "valuation": root / "data/bao_hs300_pb_2019_2026.csv",
}
snapshot = {}
for name, path in files.items():
    frame = pd.read_csv(path)
    snapshot[name] = {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": len(frame),
        "symbols": int(frame["symbol"].nunique()),
    }
snapshot["retrieved_at_utc"] = datetime.now(timezone.utc).isoformat()
snapshot["provider"] = "BaoStock 0.9.4"
snapshot["data_limits"] = [
    "monthly queried HS300 members, not daily publication-time membership",
    "retrospective forward-adjusted prices (adjustflag=2)",
    "valuation timestamps and historical revisions not independently audited",
    "no price-limit fill or order-book model",
]
out = root / "results/hs300_validation_2020_2026/data_manifest.json"
out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
print(out)
