#!/usr/bin/env bash
# Copies the public dataset of the demonstration project (dat.normand1999, as metafor
# wrote it in stats-r/fixtures/meta-analysis.json) into the backend, so the running app
# can create the demo without the R fixtures mounted. Never edit the copy by hand; a test
# checks that it matches the fixture.
set -euo pipefail
cd "$(dirname "$0")/.."
python - <<'PY'
import json
cases = json.load(open("stats-r/fixtures/meta-analysis.json", encoding="utf-8"))["cases"]
case = next(c for c in cases if c["name"] == "dat.normand1999_MD_REML_knha")
out = {
    "source": "metafor::dat.normand1999 (copied from stats-r/fixtures/meta-analysis.json, "
    "case dat.normand1999_MD_REML_knha; regenerate with scripts/export-demo-data.sh)",
    "data": case["request"]["data"],
}
path = "backend/app/modules/learning/demo_normand1999.json"
open(path, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
print("written", path)
PY
