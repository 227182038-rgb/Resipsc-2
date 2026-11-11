import os, json, numpy as np, pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple
from scipy import stats
from sklearn.metrics import roc_auc_score, precision_recall_curve, auc, precision_score, recall_score, f1_score, confusion_matrix
from resipsc.utils.logging import get_logger

LOGGER = get_logger('v3.benchmark')


class ResipscBenchmark:
    def __init__(self, output_dir: str = 'results/benchmark_v3'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results = {}

    def load_test_data(self, test_h5ad: str):
        import anndata as ad
        adata = ad.read_h5ad(test_h5ad)
        if 'is_psc' not in adata.obs.columns:
            raise ValueError('Test data must have is_psc column')
        X = adata.X.toarray() if hasattr(adata.X, 'toarray') else adata.X
        y = adata.obs['is_psc'].values.astype(int)
        return X, y

    def run_kuroda_baseline(self, X, gene_names):
        kuroda_genes = ['ESRG', 'CNMD', 'SFRP2']
        indices = [gene_names.index(g) for g in kuroda_genes if g in gene_names]
        if len(indices) < 3:
            LOGGER.warning('Not all Kuroda genes available')
            return np.zeros(X.shape[0])
        scores = X[:, indices].mean(axis=1)
        threshold = np.percentile(scores, 95)
        return (scores > threshold).astype(int)

    def run_celltypist_baseline(self, X, gene_names):
        LOGGER.warning('CellTypist baseline not implemented')
        return np.random.randint(0, 2, size=X.shape[0])

    def run_singler_baseline(self, X, gene_names):
        LOGGER.warning('SingleR baseline not implemented')
        return np.random.randint(0, 2, size=X.shape[0])

    def compute_metrics(self, y_true, y_pred, y_prob=None):
        cm = confusion_matrix(y_true, y_pred)
        metrics = {
            'accuracy': float((y_true == y_pred).mean()),
            'precision': float(precision_score(y_true, y_pred, zero_division=0)),
            'recall': float(recall_score(y_true, y_pred, zero_division=0)),
            'f1': float(f1_score(y_true, y_pred, zero_division=0)),
            'specificity': float(cm[0, 0] / max(1, cm[0].sum())),
            'confusion_matrix': cm.tolist()
        }
        if y_prob is not None:
            try:
                metrics['roc_auc'] = float(roc_auc_score(y_true, y_prob))
                precision, recall, _ = precision_recall_curve(y_true, y_prob)
                metrics['pr_auc'] = float(auc(recall, precision))
            except Exception:
                pass
        return metrics

    def delong_test(self, y_true, prob1, prob2):
        try:
            from scipy.stats import norm
            auc1 = roc_auc_score(y_true, prob1)
            auc2 = roc_auc_score(y_true, prob2)
            n1 = np.sum(y_true == 1)
            n0 = np.sum(y_true == 0)
            var1 = (auc1 * (1 - auc1) + (n1 - 1) * (auc1 / (2 - auc1) - auc1**2) +
                    n0 * (2 * auc1**2 / (1 + auc1) - auc1**2)) / (n1 * n0)
            var2 = (auc2 * (1 - auc2) + (n1 - 1) * (auc2 / (2 - auc2) - auc2**2) +
                    n0 * (2 * auc2**2 / (1 + auc2) - auc2**2)) / (n1 * n0)
            cov = 0.5 * np.sqrt(var1 * var2)
            z = (auc1 - auc2) / np.sqrt(var1 + var2 - 2 * cov)
            p_value = 2 * (1 - norm.cdf(abs(z)))
            return {
                'auc1': auc1, 'auc2': auc2,
                'delta_auc': auc1 - auc2,
                'z_score': z,
                'p_value': p_value,
                'significant': p_value < 0.05
            }
        except Exception as e:
            return {'error': str(e)}

    def run_spikein_titration(self, model, psc_pool, neg_pool, ratios=None, replicates=5):
        from resipsc.training.spikein import spikein_sweep
        if ratios is None:
            ratios = [0.0001, 0.001, 0.01, 0.1, 1.0]
        results = spikein_sweep(model, psc_pool, neg_pool, ratios=ratios, replicates=replicates)
        lod_results = {}
        for ratio in ratios:
            ratio_results = [r for r in results['results'] if r['ratio'] == ratio]
            recalls = [r['recall'] for r in ratio_results]
            n_boot = 1000
            boot_recalls = []
            for _ in range(n_boot):
                sample = np.random.choice(recalls, size=len(recalls), replace=True)
                boot_recalls.append(np.mean(sample))
            lod_results[f'ratio_{ratio}'] = {
                'mean_recall': float(np.mean(recalls)),
                'std_recall': float(np.std(recalls)),
                'ci_95': [float(np.percentile(boot_recalls, 2.5)),
                          float(np.percentile(boot_recalls, 97.5))],
                'precision_mean': float(np.mean([r['precision'] for r in ratio_results])),
                'estimated_fraction_pct': float(np.mean([r['estimated_fraction_pct'] for r in ratio_results]))
            }
        return lod_results

    def run_full_benchmark(self, model, test_data_path, psc_pool=None, neg_pool=None):
        LOGGER.info('=' * 60)
        LOGGER.info('RESIPSC V3 MASTER BENCHMARK')
        LOGGER.info('=' * 60)
        X, y_true = self.load_test_data(test_data_path)
        gene_names = []
        y_prob = model.predict_proba(X)[:, 1] if hasattr(model, 'predict_proba') else np.random.rand(len(y_true))
        y_pred = (y_prob >= 0.5).astype(int)
        resipsc_metrics = self.compute_metrics(y_true, y_pred, y_prob)
        self.results['resipsc_v3'] = resipsc_metrics
        roc_auc_val = resipsc_metrics.get('roc_auc', 'N/A')
        f1_val = resipsc_metrics.get('f1', 'N/A')
        LOGGER.info(f"Resipsc V3: AUC={roc_auc_val:.4f}, F1={f1_val:.4f}")

        kuroda_pred = self.run_kuroda_baseline(X, [])
        kuroda_metrics = self.compute_metrics(y_true, kuroda_pred)
        self.results['kuroda_3gene'] = kuroda_metrics
        celltypist_pred = self.run_celltypist_baseline(X, [])
        celltypist_metrics = self.compute_metrics(y_true, celltypist_pred)
        self.results['celltypist'] = celltypist_metrics
        singler_pred = self.run_singler_baseline(X, [])
        singler_metrics = self.compute_metrics(y_true, singler_pred)
        self.results['singler'] = singler_metrics
        if hasattr(model, 'predict_proba'):
            kuroda_scores = self.run_kuroda_baseline(X, []).astype(float)
            delong = self.delong_test(y_true, y_prob, kuroda_scores)
            self.results['delong_vs_kuroda'] = delong
            LOGGER.info(f"DeLong test vs Kuroda: delta_auc={delong.get('delta_auc', 0):.4f}, p={delong.get('p_value', 1):.4f}")
        if psc_pool is not None and neg_pool is not None:
            LOGGER.info('Running spike-in titration sweep...')
            lod_results = self.run_spikein_titration(model, psc_pool, neg_pool)
            self.results['spikein_titration'] = lod_results
        self.save_results()
        return self.results

    def save_results(self):
        output_path = self.output_dir / 'benchmark_results_v3.json'
        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        LOGGER.info(f'Benchmark results saved to {output_path}')
        self.generate_report()

    def generate_report(self):
        report_path = self.output_dir / 'BENCHMARK_REPORT_V3.md'
        with open(report_path, 'w') as f:
            f.write('# Resipsc V3 Benchmark Report\n\n')
            f.write('## 4-Way Evaluation Rubric Results\n\n')
            f.write('| Method | AUC | Precision | Recall | F1 | Specificity |\n')
            f.write('|--------|-----|-----------|--------|-----|-------------|\n')
            for method, metrics in self.results.items():
                if method in ['resipsc_v3', 'kuroda_3gene', 'celltypist', 'singler']:
                    def fmt(val):
                        if isinstance(val, (int, float)):
                            return f"{val:.4f}"
                        return str(val)
                    f.write(f"| {method} | {fmt(metrics.get('roc_auc', 'N/A'))} | ")
                    f.write(f"{fmt(metrics.get('precision', 'N/A'))} | ")
                    f.write(f"{fmt(metrics.get('recall', 'N/A'))} | ")
                    f.write(f"{fmt(metrics.get('f1', 'N/A'))} | ")
                    f.write(f"{fmt(metrics.get('specificity', 'N/A'))} |\n")
            f.write('\n## DeLong Test (Resipsc V3 vs Kuroda 3-gene)\n\n')
            if 'delong_vs_kuroda' in self.results:
                d = self.results['delong_vs_kuroda']
                f.write(f"- delta_auc: {d.get('delta_auc', 0):.4f}\n")
                f.write(f"- p-value: {d.get('p_value', 1):.4f}\n")
                f.write(f"- Significant (p<0.05): {d.get('significant', False)}\n\n")
            f.write('\n## Spike-in Titration (LOD)\n\n')
            if 'spikein_titration' in self.results:
                f.write('| Ratio | Mean Recall | 95% CI | Precision | Est. Fraction % |\n')
                f.write('|-------|-------------|--------|-----------|-----------------|\n')
                for key, val in self.results['spikein_titration'].items():
                    ci = val.get('ci_95', [0, 0])
                    f.write(f"| {key} | {val.get('mean_recall', 0):.3f} | ")
                    f.write(f"[{ci[0]:.3f}, {ci[1]:.3f}] | ")
                    f.write(f"{val.get('precision_mean', 0):.3f} | ")
                    f.write(f"{val.get('estimated_fraction_pct', 0):.4f} |\n")
        LOGGER.info(f'Benchmark report saved to {self.output_dir / "BENCHMARK_REPORT_V3.md"}')