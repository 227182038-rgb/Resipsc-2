#!/usr/bin/env python3
"""Fix Gap 2 (DeLong alignment) without re-running the full 9-minute suite."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from resipsc.config import default_config
from resipsc.data.synthetic import simulate_datasets
from resipsc.utils.io import save_json
from resipsc.utils.seed import seed_everything
from close_all_gaps import gap2_kuroda, gap7_figure

seed_everything(42)
cfg = default_config()
ads = simulate_datasets(max_cells_per_dataset=cfg.max_cells_per_dataset, seed=42)
t0 = time.time()
g2 = gap2_kuroda(ads)
save_json(g2, "results/kuroda_comparison.json")
print("gap2 fixed:", json.dumps({k: g2[k] for k in
      ("resipsc_auc", "kuroda_auc", "delong_p", "significant")}))

# rebuild figure + summary from all saved gap results
g1 = json.load(open("results/bootstrap_ci_results.json"))
g3 = json.load(open("results/ablation_results.json"))
g4 = json.load(open("results/harmony_batch_correction.json"))
g5 = json.load(open("results/multi_seed_results.json"))
g6 = {"gap": 6, "title": "Wet-lab limitation statement",
      "path": "paper/wet_lab_limitation.md", "status": "closed"}
g7 = gap7_figure({"g1": g1, "g2": g2, "g3": g3, "g4": g4, "g5": g5})

summary = {
    "title": "resipsc v2.0 — publication gap fixes",
    "generated_at_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + " UTC",
    "gaps": [g1, g2, g3, g4, g5, g6, g7],
    "all_closed": all(g["status"] == "closed" for g in (g1, g2, g3, g4, g5, g6, g7)),
    "total_runtime_seconds": round(time.time() - t0, 1),
}
save_json(summary, "results/gap_fix_summary.json")
print("all_closed:", summary["all_closed"], "| figure:", g7["paths"])
