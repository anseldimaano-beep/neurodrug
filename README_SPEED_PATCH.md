# NeuroDrug — Training Speed Patch (supersedes run_training.py / run_ablation.py from the leakage-fix patch)

## The actual bottleneck

Your log showed 37 train batches/epoch at batch_size=64, ~2.5-3 min/epoch.
The cause isn't CPU vs GPU — it's that every mini-batch re-runs the FULL
3-layer HGT encoder over the entire graph (2820 nodes, 36867 edges) just to
score 64 pairs. The graph is identical across all 37 batches in an epoch;
only the model weights are moving. That's 37x more encoder passes per epoch
than necessary.

## The fix: bigger batches = fewer redundant full-graph passes

Both scripts now accept `--batch-size` (default 4096, which exceeds the
~2400-pair training set, so training becomes 1 full-batch pass per epoch
instead of ~37). This should cut epoch time roughly 30x on the same
hardware — expect seconds instead of minutes per epoch.

## Usage

```powershell
docker-compose exec api python scripts/run_training.py
# same as: --batch-size 4096 --epochs 100 --patience 15

docker-compose exec api python scripts/run_ablation.py
# same as: --batch-size 4096 --epochs 60 --patience 12

# if you want the old mini-batch SGD behavior for any reason:
docker-compose exec api python scripts/run_training.py --batch-size 64
```

`run_baselines.py` didn't need this fix — its GCN/R-GCN/HAN training loops
already do full-batch gradient descent (no DataLoader batching), so they
were never affected by this bottleneck.

## Trade-off to know about

Full-batch gradient descent has less stochastic noise than mini-batch SGD,
which can occasionally converge to a sharper/different optimum. With only
~2400 training pairs this is a reasonable trade for CPU speed. If you
later train on a much larger graph (more diseases, more ETL'd drugs), you
may want to dial `--batch-size` back down for better generalization —
just expect training to slow back down proportionally.
