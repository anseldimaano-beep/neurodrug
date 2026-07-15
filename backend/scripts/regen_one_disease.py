"""
Regenerate predictions for a single disease and report exactly how many
candidates were persisted vs skipped (and why), without going through the
HTTP API's auth layer.

Usage:
    python scripts/regen_one_disease.py --efo-id MONDO_0019004 --model-version-id 1 --top-k 20
"""
import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from app.db.session import AsyncSessionLocal
from app.services.repurposing import DrugRepurposingService
from app.core.logging import logger


async def main(efo_id: str, model_version_id: int, top_k: int):
    async with AsyncSessionLocal() as db:
        service = DrugRepurposingService(db)
        results = await service.run_inference(
            disease_efo_id=efo_id,
            disease_mondo_id=None,
            model_version_id=model_version_id,
            top_k=top_k,
        )
        print(f"\n{'='*70}\nReturned {len(results)} ranked candidates (top_k={top_k}):")
        for r in results:
            print(f"  {r['rank']:>2}. {r['drug_name']:<30} score={r['prediction_score']:.4f}")
        print(f"{'='*70}")
        print("See the log lines above starting 'Inference complete for ...' "
              "for the persisted/skipped breakdown, and any 'not found in DB "
              "— skipping' lines for which specific drugs were dropped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--efo-id", required=True)
    parser.add_argument("--model-version-id", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args()
    asyncio.run(main(args.efo_id, args.model_version_id, args.top_k))
