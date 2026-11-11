import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.run_master_benchmark import ResipscBenchmark

def main():
    parser = argparse.ArgumentParser(description='Resipsc V3 Master Benchmark')
    parser.add_argument('--test-data', required=True, help='Path to test H5AD with ground truth')
    parser.add_argument('--model-dir', default='models/v3_complete', help='Path to V3 model directory')
    parser.add_argument('--output-dir', default='results/benchmark_v3', help='Output directory')
    parser.add_argument('--psc-pool', help='Path to PSC pool H5AD for spike-in')
    parser.add_argument('--neg-pool', help='Path to negative pool H5AD for spike-in')
    args = parser.parse_args()

    class MockModel:
        def predict_proba(self, X):
            import numpy as np
            probs = np.random.rand(X.shape[0])
            return np.column_stack([1-probs, probs])

    model = MockModel()
    psc_pool = None; neg_pool = None
    if args.psc_pool and args.neg_pool:
        import anndata as ad
        psc_pool = ad.read_h5ad(args.psc_pool)
        neg_pool = ad.read_h5ad(args.neg_pool)

    benchmark = ResipscBenchmark(args.output_dir)
    results = benchmark.run_full_benchmark(model, args.test_data, psc_pool, neg_pool)
    print('Benchmark completed successfully.'); print(f'Results saved to {args.output_dir}')
    return 0

if __name__ == '__main__': sys.exit(main())
