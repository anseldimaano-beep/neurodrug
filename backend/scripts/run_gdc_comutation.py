"""
Run GDC ETL (gene upsert + Edge type 4 Co-mutation derivation) for a single
project, synchronously, in-process — no Celery worker, no Redis required.

Usage (against local Docker Postgres):
    docker-compose exec api python scripts/run_gdc_comutation.py --project TCGA-GBM

Usage (against Neon):
    docker-compose exec \
      -e POSTGRES_HOST=<neon-host> -e POSTGRES_PORT=5432 \
      -e POSTGRES_DB=neondb -e POSTGRES_USER=neondb_owner \
      -e POSTGRES_PASSWORD=<password> -e POSTGRES_SSL=true \
      api python scripts/run_gdc_comutation.py --project TCGA-GBM --min-co-occurrences 2

NOTE: pediatric cancers (Neuroblastoma, Ewing Sarcoma, Wilms Tumor) are
generally NOT under TCGA (which is predominantly adult cancers) — they're
more likely under the TARGET program (e.g. TARGET-NBL, TARGET-WT). Confirm
the correct project code for each disease before running this for anything
other than Glioblastoma; this script does not guess that mapping for you.
"""
import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.domain import Interaction, Gene
from app.services.etl.orchestrator import ETLOrchestrator


async def main(project: str, gene_ids, min_co_occurrences: int):
    async with AsyncSessionLocal() as db:
        orch = ETLOrchestrator(db)
        job = await orch.create_job("gdc")
        print(f"Running GDC ETL for project={project} "
              f"min_co_occurrences={min_co_occurrences}...\n")
        await orch.ingest_gdc(job.id, project, gene_ids, min_co_occurrences)

        result = await db.execute(
            select(Interaction, Gene)
            .join(Gene, Gene.id == Interaction.source_gene_id)
            .where(Interaction.interaction_type == "CoMutation")
            .order_by(Interaction.confidence_score.desc())
            .limit(30)
        )
        rows = result.all()
        print(f"\nTop CoMutation edges now in the DB (showing up to 30):")
        for interaction, source_gene in rows:
            target = await db.execute(select(Gene).where(Gene.id == interaction.target_gene_id))
            target_gene = target.scalar_one_or_none()
            print(f"  {source_gene.symbol:<10} <-> {target_gene.symbol if target_gene else '?':<10}  "
                  f"co-occurred in {interaction.evidence_score:.0f} cases "
                  f"(freq={interaction.confidence_score:.3f})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="TCGA-GBM")
    parser.add_argument("--gene-ids", nargs="*", default=None)
    parser.add_argument("--min-co-occurrences", type=int, default=2)
    args = parser.parse_args()
    asyncio.run(main(args.project, args.gene_ids, args.min_co_occurrences))
