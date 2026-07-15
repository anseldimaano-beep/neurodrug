# NeuroDrug — Proposal Alignment Patch

Adds the three pieces that were missing relative to the research proposal:
HAN baseline, edge-type ablation study, and t-SNE drug-embedding visualization.

## Files (drop into your repo at the same relative paths)

- `backend/app/ml/models/baselines.py` — MODIFIED: adds `HANBaseline` and
  `HANLinkPredictor` (the import for `HANConv` was already there, unused).
- `backend/app/ml/edge_filter.py` — NEW: edge-category filtering helper used
  by the ablation script.
- `backend/scripts/run_ablation.py` — NEW: Step 3.2 ablation study
  (PPI-only / Drug-Target-only / Gene-Disease-only / PPI+Drug-Target).
- `backend/scripts/generate_tsne.py` — NEW: Step 3.4 t-SNE plot of drug
  embeddings, colored by mechanism-of-action class.
- `backend/scripts/run_baselines.py` — NEW: Step 3.1 six-baseline comparison
  (Random, Jaccard, Matrix Factorization, GCN, R-GCN, HAN) against your
  trained HGT checkpoint, with the Section F permutation test (n=1000).

## PowerShell — apply the patch

```powershell
# From your NeuroDrug repo root
Copy-Item -Path .\backend\app\ml\models\baselines.py -Destination .\backend\app\ml\models\baselines.py.bak
# Then copy the 5 files above into place (unzip this patch on top of the repo), e.g.:
Expand-Archive -Path neurodrug-proposal-alignment-patch.zip -DestinationPath . -Force
```

## Run each piece (inside the Docker container)

```powershell
docker-compose exec api python scripts/run_baselines.py --epochs 60
docker-compose exec api python scripts/run_ablation.py --epochs 60 --patience 12
docker-compose exec api python scripts/generate_tsne.py --perplexity 30 --n-iter 1000
```

Outputs land in `checkpoints/`:
- `baseline_comparison.json` (+ printed leaderboard table)
- `ablation_results.json` (+ printed ΔAUC table)
- `drug_tsne.png` and `drug_tsne_coords.json`

## Known gap not covered by this patch

The proposal's "co-mutation" Gene-Gene edge type (TCGA-derived) isn't
populated by `services/etl/gdc.py` yet, so `run_ablation.py` covers PPI,
Drug-Target, and Gene-Disease only. Extending the GDC client to derive
co-occurrence edges from the somatic mutation records it already ingests
would close this gap — flagged in the proposal addendum too.
