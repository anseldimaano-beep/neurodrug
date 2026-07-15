# NeuroDrug — Leakage Fix + docker-compose Volume Fix

Second patch. Fixes two real bugs found while reviewing your first ablation/
baseline run results:

## 1. Transductive edge leakage (the important one)

`nx_to_heterodata` puts every Drug-Disease edge — train AND validation —
into the graph used for message passing. That let the encoder "see" the
exact edges it was later evaluated on, which explains last run's backwards
results (removing edge types improved AUC; R-GCN/HAN beat HGT).

**Fix:** `backend/app/ml/edge_filter.py` gets two new functions,
`mask_target_edges()` and `override_edge_index_dict()`, which strip
validation-positive Drug-Disease edges (both directions) out of the
message-passing graph before training or evaluating ANY model. Wired into:

- `backend/scripts/run_training.py` — the main HGT training run
- `backend/scripts/run_ablation.py` — masking applied before category filtering
- `backend/scripts/run_baselines.py` — masking applied to HGT eval, GCN, R-GCN, and HAN alike

## 2. docker-compose.yml duplicate/mismatched volume mount

`api` mounted both a named volume AND a bind mount to the same container
path (`/app/checkpoints`) — worked by accident (bind mount wins), but
`worker` only had the named volume, meaning any Celery-dispatched training
job would write to storage invisible to `api` and your host. Fixed: both
services now mount `./checkpoints:/app/checkpoints`, and the unused named
volume declaration is removed.

## Files (drop into your repo at the same relative paths)

- `docker-compose.yml` — MODIFIED (see diff below — check you haven't
  customized this file yourself before overwriting)
- `backend/app/ml/edge_filter.py` — MODIFIED (adds masking functions)
- `backend/scripts/run_training.py` — MODIFIED (applies the fix)
- `backend/scripts/run_ablation.py` — MODIFIED (applies the fix)
- `backend/scripts/run_baselines.py` — MODIFIED (applies the fix)

`generate_tsne.py` is untouched — it only reads embeddings from an existing
checkpoint, doesn't train, so there's no leakage question there.

## PowerShell — apply and clean up

```powershell
cd C:\path\to\your\NeuroDrug\repo

# back up before overwriting
Copy-Item docker-compose.yml docker-compose.yml.bak

# unzip this patch on top of the repo
Expand-Archive -Path neurodrug-leakage-fix-patch.zip -DestinationPath . -Force

# delete the orphaned stale checkpoint folder found during review
Remove-Item -Recurse -Force .\backend\checkpoints

# recreate containers with the fixed compose file
docker-compose down
docker-compose up -d
```

## IMPORTANT — you must retrain, not just rerun evaluation

Your existing `checkpoints/best_model.pt` was trained BEFORE this fix, on
the leaky graph — its weights may have partly learned to exploit the leak.
Re-running `run_baselines.py` against that old checkpoint will not give you
a trustworthy HGT number. Retrain first:

```powershell
docker-compose exec api python scripts/run_training.py
docker-compose exec api python scripts/run_baselines.py --epochs 60
docker-compose exec api python scripts/run_ablation.py --epochs 60 --patience 12
```

Expect different (likely lower, more honest) absolute AUC numbers than last
time, and — if the fix worked — the ablation ordering should flip back to
something biologically sensible (full_model >= any single edge-type-only
variant), rather than the inverted pattern from before.
