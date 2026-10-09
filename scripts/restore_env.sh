#!/usr/bin/env bash
# restore_env.sh — one-command recovery after a sandbox/venv reset.
# The platform occasionally rebuilds the container and resets /home/z/.venv
# to its base template (drops anndata, h5py, pandas, xgboost, harmonypy,
# reportlab + the sitecustomize.py pydantic fix). This script restores both.
#
# Usage:  bash /home/z/my-project/scripts/restore_env.sh

set -euo pipefail

VENV_SITE=/home/z/.venv/lib/python3.12/site-packages
PROJ=/home/z/my-project

echo "[restore] 1/2  installing pinned ML stack into /home/z/.venv ..."
uv pip install -r "$PROJ/requirements.txt" --python /home/z/.venv/bin/python3

echo "[restore] 2/2  restoring sitecustomize.py (PART 3.1 pydantic fix) ..."
if [ -f "$PROJ/scripts/sitecustomize.py" ]; then
    cp "$PROJ/scripts/sitecustomize.py" "$VENV_SITE/sitecustomize.py"
    echo "[restore]   -> copied to $VENV_SITE/sitecustomize.py"
else
    echo "[restore]   !! canonical copy missing: $PROJ/scripts/sitecustomize.py" >&2
    exit 1
fi

echo "[restore] verifying ..."
DATABASE_URL="file:./db/custom.db" /home/z/.venv/bin/python3 - <<'PY'
import sys; sys.path.insert(0, "/home/z/my-project")
import warnings; warnings.filterwarnings("ignore")
import anndata, pandas, sklearn, xgboost, h5py, harmonypy, reportlab
import pickle
with open("/home/z/my-project/results/final_model.pkl", "rb") as f:
    m = pickle.load(f)
a = anndata.read_h5ad("/home/z/my-project/results/golden_batch.h5ad")
rep = m.qc_report_dict(a, batch_id="RESTORE-CHECK", input_file="golden_batch.h5ad")
assert rep["decision"] in {"PASS", "HOLD", "QUARANTINE"}, rep["decision"]
print(f"[restore] OK: anndata {anndata.__version__} | model unpickles | QC -> {rep['decision']}")
PY

echo "[restore] DONE. If the Next.js server was already running it will pick up"
echo "[restore] the packages on the next QC run (python is spawned per request)."
