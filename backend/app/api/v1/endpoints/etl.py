from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.api.deps import get_db, get_current_active_user, require_role
from app.models.domain import User, ETLJob, DataSource
from app.schemas.etl import ETLJobResponse
from app.services.etl.orchestrator import ETLOrchestrator
from app.tasks.etl_tasks import (
    run_etl_opentargets, run_etl_string, run_etl_dgidb,
    run_etl_chembl, run_etl_uniprot, run_etl_clinicaltrials, run_etl_gdc,
)
from app.core.logging import logger

router = APIRouter()

# FIX C9: per-disease driver gene panels, per the project's data-collection
# spec (COSMIC Cancer Gene Census, 40 genes across 5 disease types). This
# replaces a single flat 16-gene list that was applied identically to every
# disease regardless of relevance — under that scheme, Ewing Sarcoma and
# Wilms Tumor had ZERO of their defining driver genes (EWSR1/FLI1/ERG and
# WT1 were entirely absent), so those two diseases got no STRING/DGIdb
# signal at all, only whatever OpenTargets happened to surface per-disease.
#
# NOTE: only genes explicitly confirmed against the project spec are listed
# below. The spec calls for 40 genes total (COSMIC Cancer Gene Census) but
# only named ~18 unique genes across the 5 diseases in the excerpt used to
# build this list — the remaining genes needed to reach 40 have NOT been
# added, to avoid fabricating gene-disease associations. Add them here once
# the full 40-gene list is confirmed.
_DISEASE_DRIVER_GENES = {
    "glioblastoma":    ["EGFR", "PTEN", "IDH1", "NF1", "RB1", "PDGFRA"],
    "neuroblastoma":   ["MYCN", "ALK", "PHOX2B", "ATRX"],
    "medulloblastoma": ["PTCH1", "SMO", "CTNNB1", "MYC"],
    "ewing sarcoma":   ["EWSR1", "FLI1", "ERG"],
    "wilms tumor":     ["WT1", "CTNNB1"],
}

# Genes from the old flat list NOT confirmed against the spec excerpt above.
# Kept available but NOT auto-assigned to any disease — these may belong to
# the remaining ~22 genes needed to reach the spec's 40-gene total, but
# without the full COSMIC list we can't say which disease(s) they belong to.
_UNVERIFIED_PAN_CANCER_GENES = [
    "TP53", "IDH2", "BRAF", "KRAS", "PIK3CA", "CDKN2A", "VHL",
]

# NOTE: CHEMBL614 (Pyrazinamide — a tuberculosis drug, unrelated to any of
# the five cancers this project covers) used to be in this list. It was an
# accidental collision with Temozolomide's *incorrect* seeded chembl_id,
# which was also CHEMBL614 — meaning every time this default list ran, the
# ChEMBL ETL upsert (matches by chembl_id) found the existing Temozolomide
# row and silently renamed it "PYRAZINAMIDE" in place. Temozolomide's real
# ChEMBL ID is CHEMBL810 (now fixed in seed_initial_data.py). Removed here.
_CANCER_CHEMBL_IDS = [
    "CHEMBL1201583","CHEMBL941","CHEMBL535",
    "CHEMBL25","CHEMBL1421","CHEMBL2068237",
]


@router.post("/ingest/all_diseases", status_code=status.HTTP_202_ACCEPTED)
async def ingest_all_diseases(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("researcher")),
):
    """
    Queue OpenTargets + ClinicalTrials + STRING + DGIdb ETL for every
    disease currently in the DB, using that disease's own driver gene
    panel (see _DISEASE_DRIVER_GENES) for the gene-centric sources.

    FIX C8: this previously only queued OpenTargets + ClinicalTrials, so Gene
    nodes never populated — STRING (Gene-Gene) and DGIdb (Drug-Gene) were
    never triggered by this endpoint at all.
    FIX C9: STRING/DGIdb previously ran ONCE over a single shared gene list
    applied to every disease. Now each disease gets its own confirmed driver
    panel, so e.g. Ewing Sarcoma's STRING/DGIdb jobs actually run over
    EWSR1/FLI1/ERG instead of a generic list that didn't include them.

      - OpenTargets: passes the MONDO ID stored on each Disease row directly
        as efoId — Open Targets' GraphQL API accepts MONDO-format IDs natively.
      - ClinicalTrials: uses the disease name as the condition search term.
      - STRING / DGIdb: run once per disease, over that disease's own
        confirmed driver gene panel.
    """
    from sqlalchemy import select as _select
    from app.models.domain import Disease as _Disease

    result = await db.execute(_select(_Disease).where(_Disease.is_deleted == False))
    diseases = result.scalars().all()

    orch = ETLOrchestrator(db)
    queued = []
    for disease in diseases:
        efo_id = disease.efo_id
        condition = disease.name.lower()
        gene_panel = _DISEASE_DRIVER_GENES.get(condition, [])
        if not gene_panel:
            logger.warning(
                f"[ETL] no confirmed driver gene panel for '{disease.name}' — "
                f"STRING/DGIdb will be skipped for this disease. Add it to "
                f"_DISEASE_DRIVER_GENES."
            )

        ot_job = await orch.create_job("opentargets")
        run_etl_opentargets.delay(ot_job.id, efo_id)

        ct_job = await orch.create_job("clinicaltrials")
        run_etl_clinicaltrials.delay(ct_job.id, condition)

        job_ids = {
            "disease": disease.name,
            "efo_id": efo_id,
            "opentargets_job_id": ot_job.id,
            "clinicaltrials_job_id": ct_job.id,
            "gene_panel": gene_panel,
        }

        if gene_panel:
            string_job = await orch.create_job("string")
            run_etl_string.delay(string_job.id, gene_panel, 700)
            dgidb_job = await orch.create_job("dgidb")
            run_etl_dgidb.delay(dgidb_job.id, gene_panel)
            job_ids["string_job_id"] = string_job.id
            job_ids["dgidb_job_id"] = dgidb_job.id

        queued.append(job_ids)
        logger.info(
            f"[ETL] queued OT job={ot_job.id} + CT job={ct_job.id} for "
            f"{disease.name} (gene panel: {gene_panel or 'NONE — unconfirmed'})"
        )

    return {"queued": queued, "total": len(queued)}


@router.post("/ingest/opentargets", status_code=status.HTTP_202_ACCEPTED)
async def ingest_opentargets(
    efo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("researcher")),
):
    """Trigger OpenTargets ETL for a disease EFO ID (e.g. EFO_0000519)."""
    orch = ETLOrchestrator(db)
    job = await orch.create_job("opentargets")
    run_etl_opentargets.delay(job.id, efo_id)
    return {"job_id": job.id, "status": "queued", "source": "opentargets", "efo_id": efo_id}


@router.post("/ingest/string", status_code=status.HTTP_202_ACCEPTED)
async def ingest_string(
    gene_symbols: List[str] = None,
    min_score: int = 700,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("researcher")),
):
    """Trigger STRING PPI ETL. Defaults to known cancer genes if none supplied."""
    genes = gene_symbols or _CANCER_GENES
    orch = ETLOrchestrator(db)
    job = await orch.create_job("string")
    run_etl_string.delay(job.id, genes, min_score)
    return {"job_id": job.id, "status": "queued", "source": "string", "genes": genes}


@router.post("/ingest/dgidb", status_code=status.HTTP_202_ACCEPTED)
async def ingest_dgidb(
    gene_symbols: List[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("researcher")),
):
    """Trigger DGIdb drug–gene interaction ETL."""
    genes = gene_symbols or _CANCER_GENES
    orch = ETLOrchestrator(db)
    job = await orch.create_job("dgidb")
    run_etl_dgidb.delay(job.id, genes)
    return {"job_id": job.id, "status": "queued", "source": "dgidb", "genes": genes}


@router.post("/ingest/chembl", status_code=status.HTTP_202_ACCEPTED)
async def ingest_chembl(
    chembl_ids: List[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("researcher")),
):
    """Trigger ChEMBL drug properties ETL."""
    ids = chembl_ids or _CANCER_CHEMBL_IDS
    orch = ETLOrchestrator(db)
    job = await orch.create_job("chembl")
    run_etl_chembl.delay(job.id, ids)
    return {"job_id": job.id, "status": "queued", "source": "chembl", "chembl_ids": ids}


@router.post("/ingest/uniprot", status_code=status.HTTP_202_ACCEPTED)
async def ingest_uniprot(
    query: str = "glioblastoma cancer gene",
    size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("researcher")),
):
    """Trigger UniProt protein annotation ETL."""
    orch = ETLOrchestrator(db)
    job = await orch.create_job("uniprot")
    run_etl_uniprot.delay(job.id, query, size)
    return {"job_id": job.id, "status": "queued", "source": "uniprot", "query": query}


@router.post("/ingest/clinicaltrials", status_code=status.HTTP_202_ACCEPTED)
async def ingest_clinicaltrials(
    condition: str = "glioblastoma",
    intervention: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("researcher")),
):
    """Trigger ClinicalTrials.gov ETL for a disease condition."""
    orch = ETLOrchestrator(db)
    job = await orch.create_job("clinicaltrials")
    run_etl_clinicaltrials.delay(job.id, condition, intervention)
    return {"job_id": job.id, "status": "queued", "source": "clinicaltrials", "condition": condition}


@router.post("/ingest/gdc", status_code=status.HTTP_202_ACCEPTED)
async def ingest_gdc(
    project: str = "TCGA-GBM",
    gene_ids: List[str] = None,
    min_co_occurrences: int = 2,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("researcher")),
):
    """
    Trigger GDC/TCGA somatic mutation ETL for a TCGA project. Also derives
    Edge type 4 — Co-mutation edges from genes mutated together in the same
    patient case; min_co_occurrences sets how many distinct cases a gene
    pair must co-occur in before an edge is created (default 2, to filter
    out single-patient coincidences).
    """
    orch = ETLOrchestrator(db)
    job = await orch.create_job("gdc")
    run_etl_gdc.delay(job.id, project, gene_ids, min_co_occurrences)
    return {"job_id": job.id, "status": "queued", "source": "gdc", "project": project}


@router.get("/jobs", response_model=List[ETLJobResponse])
async def list_jobs(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(ETLJob).order_by(ETLJob.id.desc()).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/jobs/{job_id}", response_model=ETLJobResponse)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(ETLJob).where(ETLJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.get("/sources")
async def list_data_sources(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(DataSource))
    return result.scalars().all()
