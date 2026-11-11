import os, zarr, numpy as np, torch
from pathlib import Path
from typing import Iterator, Tuple, Optional
from resipsc.config.v3_settings import settings
from resipsc.utils.logging import get_logger

LOGGER = get_logger('v3.streaming.engine')
CHUNK_SIZE = settings.CHUNK_SIZE

class StreamingInferenceEngine:
    def __init__(self, model_bundle: dict, chunk_size: int = CHUNK_SIZE):
        self.scvi_model = model_bundle['scvi']
        self.gating_model = model_bundle['gating']
        self.device = model_bundle['device']
        self.chunk_size = chunk_size
        self.gating_model.to(self.device)
        self.gating_model.eval()

    def predict_h5ad_streaming(self, h5ad_path: str) -> dict:
        import anndata as ad
        LOGGER.info(f'Streaming inference on {h5ad_path}')
        adata = ad.read_h5ad(h5ad_path)
        n_cells = adata.n_obs
        all_probs = []; all_aleatoric = []; all_epistemic = []; all_alphas = []
        for i in range(0, n_cells, self.chunk_size):
            end = min(i + self.chunk_size, n_cells)
            chunk = adata[i:end].copy()
            LOGGER.info(f'  Processing chunk {i//self.chunk_size + 1}: cells {i}-{end}')
            latent = self.scvi_model.get_latent(chunk)
            latent_tensor = torch.tensor(latent, dtype=torch.float32).to(self.device)
            with torch.no_grad(): outputs = self.gating_model(latent_tensor)
            probs = outputs['prob_psc'].cpu().numpy().flatten()
            aleatoric = outputs['aleatoric_uncertainty'].cpu().numpy().flatten()
            epistemic = outputs['epistemic_uncertainty'].cpu().numpy().flatten()
            alphas = outputs['alphas'].cpu().numpy()
            all_probs.append(probs); all_aleatoric.append(aleatoric)
            all_epistemic.append(epistemic); all_alphas.append(alphas)
        return {'prob_psc': np.concatenate(all_probs), 'aleatoric': np.concatenate(all_aleatoric), 'epistemic': np.concatenate(all_epistemic), 'alphas': np.vstack(all_alphas), 'n_cells': n_cells}

    def predict_zarr_streaming(self, zarr_path: str) -> dict:
        return {'status': 'zarr_streaming_not_fully_implemented'}

def convert_h5ad_to_zarr(h5ad_path: str, output_dir: str, chunk_size: int = CHUNK_SIZE) -> str:
    import anndata as ad
    LOGGER.info(f'Converting {h5ad_path} to Zarr at {output_dir}')
    adata = ad.read_h5ad(h5ad_path)
    output_path = Path(output_dir); output_path.mkdir(parents=True, exist_ok=True)
    zarr_path = str(output_path / 'data.zarr')
    store = zarr.open(zarr_path, mode='w')
    n_cells, n_genes = adata.X.shape
    x_arr = store.create('X', shape=(n_cells, n_genes), chunks=(chunk_size, n_genes), dtype='float32', compressor=zarr.Blosc(cname='zstd', clevel=3))
    for i in range(0, n_cells, chunk_size):
        end = min(i + chunk_size, n_cells)
        chunk_X = adata.X[i:end]
        if hasattr(chunk_X, 'toarray'): chunk_X = chunk_X.toarray()
        x_arr[i:end] = chunk_X.astype(np.float32)
    obs_df = adata.obs.astype(str)
    for col in obs_df.columns: store[f'obs/{col}'] = obs_df[col].values
    var_df = adata.var.astype(str)
    for col in var_df.columns: store[f'var/{col}'] = var_df[col].values
    import json
    uns_group = store.create_group('uns')
    for key, val in adata.uns.items():
        try: uns_group[key] = json.dumps(val) if not isinstance(val, (str, int, float, bool, list, dict)) else val
        except: pass
    LOGGER.info(f'Zarr conversion complete: {zarr_path}')
    return zarr_path
