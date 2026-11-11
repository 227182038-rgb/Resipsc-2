import os, uuid, json, time
from pathlib import Path
from typing import Dict, Any
import numpy as np
from celery import shared_task
from src.api.celery_app import celery_app
from resipsc.config.v3_settings import settings
from resipsc.utils.logging import get_logger

LOGGER = get_logger('v3.tasks')
_model_cache = {}

def get_v3_model(model_dir: str = None):
    global _model_cache
    cache_key = model_dir or settings.MODEL_DIR
    if cache_key in _model_cache: return _model_cache[cache_key]
    import torch
    from resipsc.models.scvi_trainer import ResipscSCVI
    from resipsc.models.gating_layer import HierarchicalGatingNet, build_v3_gating_model
    model_path = Path(model_dir or settings.MODEL_DIR) / 'v3_complete'
    scvi_model = ResipscSCVI.load(str(model_path / 'scvi'))
    gating_checkpoint = torch.load(model_path / 'gating_net.pt', map_location='cpu')
    gene_panel = gating_checkpoint['gene_panel']
    gating_model = build_v3_gating_model(gene_panel)
    gating_model.load_state_dict(gating_checkpoint['model_state_dict'])
    gating_model.eval()
    bundle = {'scvi': scvi_model, 'gating': gating_model, 'panel': gene_panel, 'device': 'cuda' if torch.cuda.is_available() and settings.USE_GPU else 'cpu'}
    _model_cache[cache_key] = bundle
    LOGGER.info(f'Loaded V3 model from {model_path} on {bundle[\
device\]}')
    return bundle

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_inference_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
    job_id = job_data['job_id']; batch_id = job_data['batch_id']; file_path = job_data['file_path']; config = job_data.get('config', {})
    LOGGER.info(f'Starting inference job {job_id} for batch {batch_id}'); start_time = time.time()
    try:
        self.update_state(state='PROGRESS', meta={'stage': 'loading_data', 'progress': 10})
        import anndata as ad
        adata = ad.read_h5ad(file_path)
        self.update_state(state='PROGRESS', meta={'stage': 'preprocessing', 'progress': 30})
        model_bundle = get_v3_model(config.get('model_dir'))
        scvi_model = model_bundle['scvi']; gating_model = model_bundle['gating']; device = model_bundle['device']
        self.update_state(state='PROGRESS', meta={'stage': 'scvi_encoding', 'progress': 50})
        import torch
        latent = scvi_model.get_latent(adata)
        latent_tensor = torch.tensor(latent, dtype=torch.float32).to(device)
        self.update_state(state='PROGRESS', meta={'stage': 'gating_inference', 'progress': 70})
        gating_model.to(device); gating_model.eval()
        with torch.no_grad(): outputs = gating_model(latent_tensor)
        prob_psc = outputs['prob_psc'].cpu().numpy().flatten()
        aleatoric = outputs['aleatoric_uncertainty'].cpu().numpy().flatten()
        epistemic = outputs['epistemic_uncertainty'].cpu().numpy().flatten()
        alphas = outputs['alphas'].cpu().numpy()
        threshold = config.get('decision_threshold', settings.DECISION_THRESHOLD)
        is_psc = prob_psc >= threshold
        n_cells = len(prob_psc); psc_count = int(np.sum(is_psc)); psc_fraction = float(psc_count / n_cells) if n_cells > 0 else 0.0
        self.update_state(state='PROGRESS', meta={'stage': 'generating_report', 'progress': 90})
        results_dir = Path(settings.RESULTS_DIR) / batch_id; results_dir.mkdir(parents=True, exist_ok=True)
        report = {'schema_version': '3.0', 'job_id': job_id, 'batch_id': batch_id, 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'input_file': file_path, 'model_version': '3.0.0', 'summary': {'n_cells': n_cells, 'psc_count': psc_count, 'psc_fraction': psc_fraction, 'decision_threshold': threshold}, 'uncertainty': {'mean_aleatoric': float(np.mean(aleatoric)), 'mean_epistemic': float(np.mean(epistemic)), 'high_epistemic_fraction': float(np.mean(epistemic > 0.5))}, 'predictions': {'prob_psc': prob_psc.tolist(), 'is_psc': is_psc.astype(int).tolist(), 'aleatoric': aleatoric.tolist(), 'epistemic': epistemic.tolist()}, 'processing_time_seconds': time.time() - start_time}
        report_path = results_dir / f'report_{job_id}.json'
        with open(report_path, 'w') as f: json.dump(report, f, indent=2)
        np.savez_compressed(results_dir / f'predictions_{job_id}.npz', prob_psc=prob_psc, is_psc=is_psc, aleatoric=aleatoric, epistemic=epistemic, alphas=alphas)
        LOGGER.info(f'Job {job_id} completed in {time.time() - start_time:.1f}s. PSC: {psc_count}/{n_cells}')
        return {'status': 'success', 'job_id': job_id, 'report_path': str(report_path), 'psc_count': psc_count, 'psc_fraction': psc_fraction, 'n_cells': n_cells}
    except Exception as exc:
        LOGGER.error(f'Job {job_id} failed: {exc}', exc_info=True)
        raise self.retry(exc=exc)

@shared_task
def health_check_task() -> Dict[str, Any]:
    try:
        import torch
        model_bundle = get_v3_model()
        return {'status': 'healthy', 'model_loaded': True, 'device': model_bundle['device'], 'gpu_available': torch.cuda.is_available()}
    except Exception as e: return {'status': 'unhealthy', 'error': str(e)}
