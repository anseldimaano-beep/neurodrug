"""
Run the full ETL pipeline (OpenTargets + ClinicalTrials per disease, plus
one shared STRING + DGIdb pass over the cancer gene panel) synchronously,
in-process — no Celery worker, no Redis, no auth token required.

This mirrors exactly what POST /api/v1/etl/ingest/all_diseases queues via
Celery .delay(), just run directly and sequentially so you can watch it in
one terminal and point it at any DB via the usual env var overrides.

Usage (against local Docker Postgres):
    docker-compose exec api python scripts/run_etl_all.py

Usage (against Neon, from your local machine):
    docker-compose exec \
      -e POSTGRES_HOST=<neon-host> -e POSTGRES_PORT=5432 \
      -e POSTGRES_DB=neondb -e POSTGRES_USER=neondb_owner \
      -e POSTGRES_PASSWORD=<password> -e POSTGRES_SSL=true \
      api python scripts/run_etl_all.py

Add --chembl to also run the ChEMBL drug-ingestion pass (off by default
since seed_initial_data.py may already have your drug catalog with correct
chembl_ids — re-running ChEMBL ingestion will upsert by chembl_id and could
overwrite fields on existing rows).
"""
import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.domain import Disease
from app.services.etl.orchestrator import ETLOrchestrator
from app.core.logging import logger

_DISEASE_DRIVER_GENES = {
    "glioblastoma":    ["EGFR", "PTEN", "IDH1", "NF1", "RB1", "PDGFRA"],
    "neuroblastoma":   ["MYCN", "ALK", "PHOX2B", "ATRX"],
    "medulloblastoma": ["PTCH1", "SMO", "CTNNB1", "MYC"],
    "ewing sarcoma":   ["EWSR1", "FLI1", "ERG"],
    "wilms tumor":     ["WT1", "CTNNB1"],
}
# Genes from the old shared list not confirmed against the project's spec —
# not auto-assigned to any disease. See etl.py for details.
_UNVERIFIED_PAN_CANCER_GENES = [
    "TP53", "IDH2", "BRAF", "KRAS", "PIK3CA", "CDKN2A", "VHL",
]
_CANCER_CHEMBL_IDS = [
    "CHEMBL1201583", "CHEMBL941", "CHEMBL535",
    "CHEMBL25", "CHEMBL1421", "CHEMBL2068237",
]


async def main(run_chembl: bool):
    async with AsyncSessionLocal() as db:
        orch = ETLOrchestrator(db)

        result = await db.execute(select(Disease).where(Disease.is_deleted == False))
        diseases = result.scalars().all()
        if not diseases:
            print("No diseases found — run seed_initial_data.py first.")
            return

        print(f"Found {len(diseases)} diseases. Running OpenTargets + "
              f"ClinicalTrials + STRING + DGIdb (per-disease gene panels) "
              f"for each...\n")

        for disease in diseases:
            efo_id = disease.efo_id
            condition = disease.name.lower()
            gene_panel = _DISEASE_DRIVER_GENES.get(condition, [])

            print(f"--- {disease.name} ({efo_id}) ---")
            print(f"  Driver gene panel: {gene_panel or 'NONE — not in _DISEASE_DRIVER_GENES'}")

            ot_job = await orch.create_job("opentargets")
            try:
                await orch.ingest_opentargets(ot_job.id, efo_id)
                print(f"  OpenTargets OK (job {ot_job.id})")
            except Exception as e:
                print(f"  OpenTargets FAILED: {e}")

            ct_job = await orch.create_job("clinicaltrials")
            try:
                await orch.ingest_clinicaltrials(ct_job.id, condition)
                print(f"  ClinicalTrials OK (job {ct_job.id})")
            except Exception as e:
                print(f"  ClinicalTrials FAILED: {e}")

            if not gene_panel:
                print(f"  Skipping STRING/DGIdb — no confirmed gene panel for this disease.")
                continue

            string_job = await orch.create_job("string")
            try:
                await orch.ingest_string(string_job.id, gene_panel, 700)
                print(f"  STRING OK (job {string_job.id}, {len(gene_panel)} genes)")
            except Exception as e:
                print(f"  STRING FAILED: {e}")

            dgidb_job = await orch.create_job("dgidb")
            try:
                await orch.ingest_dgidb(dgidb_job.id, gene_panel)
                print(f"  DGIdb OK (job {dgidb_job.id}, {len(gene_panel)} genes)")
            except Exception as e:
                print(f"  DGIdb FAILED: {e}")

        if run_chembl:
            print(f"\n--- ChEMBL over {len(_CANCER_CHEMBL_IDS)} drug IDs ---")
            chembl_job = await orch.create_job("chembl")
            try:
                await orch.ingest_chembl(chembl_job.id, _CANCER_CHEMBL_IDS)
                print(f"  ChEMBL OK (job {chembl_job.id})")
            except Exception as e:
                print(f"  ChEMBL FAILED: {e}")

        print("\nDone. Note: _UNVERIFIED_PAN_CANCER_GENES "
              f"({_UNVERIFIED_PAN_CANCER_GENES}) were NOT run — add them to "
              "a disease's panel once confirmed against your spec, or run "
              "manually via orch.ingest_string()/ingest_dgidb().")
        print("Check node/edge counts via the Knowledge Graph Explorer, or "
              "query genes/drugs/interactions tables directly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chembl", action="store_true",
                         help="Also run ChEMBL drug ingestion (off by default)")
    args = parser.parse_args()
    asyncio.run(main(args.chembl))
