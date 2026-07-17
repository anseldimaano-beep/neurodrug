"""
Run cBioPortal ETL (gene upsert + Edge type 4 Co-mutation derivation) for a
single study, synchronously, in-process. Use this for diseases with no
public GDC/TARGET project (Ewing Sarcoma, Medulloblastoma).

Find the correct study_id first with search_cbioportal_studies.py — do not
guess it.

Usage (against local Docker Postgres):
    docker-compose exec api python scripts/run_cbioportal_comutation.py \
        --study-id <studyId> --gene-ids EWSR1 FLI1 ERG

Usage (against Neon):
    docker-compose exec \
      -e POSTGRES_HOST=<neon-host> -e POSTGRES_PORT=5432 \
      -e POSTGRES_DB=neondb -e POSTGRES_USER=neondb_owner \
      -e POSTGRES_PASSWORD=<password> -e POSTGRES_SSL=true \
      api python scripts/run_cbioportal_comutation.py \
        --study-id <studyId> --gene-ids EWSR1 FLI1 ERG --min-co-occurrences 2
"""
import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.domain import Interaction, Gene
from app.services.etl.orchestrator import ETLOrchestrator


async def main(study_id: str, gene_ids, min_co_occurrences: int):
    async with AsyncSessionLocal() as db:
        orch = ETLOrchestrator(db)
        job = await orch.create_job("cbioportal")
        print(f"Running cBioPortal ETL for study_id={study_id} "
              f"min_co_occurrences={min_co_occurrences}...\n")
        await orch.ingest_cbioportal(job.id, study_id, gene_ids, min_co_occurrences)

        result = await db.execute(
            select(Interaction, Gene)
            .join(Gene, Gene.id == Interaction.source_gene_id)
            .where(Interaction.interaction_type == "CoMutation",
                   Interaction.source_database == "cBioPortal")
            .order_by(Interaction.confidence_score.desc())
            .limit(30)
        )
        rows = result.all()
        print(f"\ncBioPortal-derived CoMutation edges now in the DB (showing up to 30):")
        for interaction, source_gene in rows:
            target = await db.execute(select(Gene).where(Gene.id == interaction.target_gene_id))
            target_gene = target.scalar_one_or_none()
            print(f"  {source_gene.symbol:<10} <-> {target_gene.symbol if target_gene else '?':<10}  "
                  f"co-occurred in {interaction.evidence_score:.0f} patients "
                  f"(freq={interaction.confidence_score:.3f})")

        if not rows:
            print("\nNo edges found — printing raw structural variant records for debugging:")
            from app.services.etl.cbioportal import CBioPortalClient
            async with CBioPortalClient() as dbg_client:
                svs = await dbg_client.get_structural_variants(study_id, gene_ids or [])
            for sv in svs[:5]:
                print(f"  {sv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--study-id", required=True)
    parser.add_argument("--gene-ids", nargs="*", default=None)
    parser.add_argument("--min-co-occurrences", type=int, default=2)
    args = parser.parse_args()
    asyncio.run(main(args.study_id, args.gene_ids, args.min_co_occurrences))
