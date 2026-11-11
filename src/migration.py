"""
V2 to V3 Migration Utilities
Tools for converting V2 artifacts (models, reports, configs) to V3 format.
"""

import json
import pickle
from pathlib import Path
from typing import Any, Dict
import numpy as np

def migrate_v2_config(v2_config_path: str) -> Dict[str, Any]:
    """Extract relevant settings from V2 Config class."""
    # V2 Config is a simple class, we read attributes
    import importlib.util
    spec = importlib.util.spec_from_file_location(\"config\", v2_config_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    config = module.Config()
    return {
        \"n_hvg\": config.n_hvg,
        \"random_state\": config.random_state,
        \"xgb_weight\": config.xgb_weight,
        \"deep_weight\": config.deep_weight,
        \"decision_threshold\": config.decision_threshold,
        \"results_dir\": config.results_dir,
    }

def migrate_v2_model(v2_model_path: str, output_dir: str) -> str:
    """Convert V2 pickle to V3 model format."""
    # V2 models are pickled ResipscEnsemble objects
    # V3 format separates weights, architecture, and metadata
    output_path = Path(output_dir) / \"migrated_v3_model\"
    output_path.mkdir(parents=True, exist_ok=True)
    
    # This is a template - actual migration requires the model class definition
    metadata = {
        \"format_version\": \"3.0\",
        \"source\": \"v2_pickle\",
        \"model_type\": \"hybrid_ensemble\",
        \"architecture\": {
            \"classical\": {\"xgb\": True, \"rf\": True, \"svm\": True},
            \"deep\": {\"ae_mlp\": True},
            \"transformer\": False
        },
        \"weights_path\": \"weights.npz\",
        \"scaler_path\": \"scaler.npz\"
    }
    
    with open(output_path / \"metadata.json\", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    return str(output_path)

def migrate_v2_report(v2_report_path: str) -> Dict[str, Any]:
    """Convert V2 report format to V3 standardized schema."""
    with open(v2_report_path, 'r') as f:
        v2_report = json.load(f)
    
    # Map V2 fields to V3 schema
    v3_report = {
        \"schema_version\": \"3.0\",
        \"batch_id\": v2_report.get(\"batch_id\", \"UNKNOWN\"),
        \"timestamp\": v2_report.get(\"timestamp\", \"\"),
        \"input_file\": v2_report.get(\"input_file\", \"\"),
        \"model_info\": {
            \"version\": v2_report.get(\"model_version\", \"2.0.0\"),
            \"type\": \"hybrid_ensemble_v2\"
        },
        \"summary\": {
            \"n_cells\": v2_report.get(\"n_cells\", 0),
            \"psc_fraction\": v2_report.get(\"estimated_psc_fraction\", 0.0),
            \"psc_count\": v2_report.get(\"estimated_psc_count\", 0),
            \"detection_threshold\": v2_report.get(\"decision_threshold\", 0.5)
        },
        \"quality_metrics\": v2_report.get(\"quality_metrics\", {}),
        \"uncertainty\": v2_report.get(\"uncertainty\", {}),
        \"regulatory\": v2_report.get(\"regulatory_context\", {}),
        \"raw_v2\": v2_report  # Preserve original for audit trail
    }
    
    return v3_report
