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

_CANCER_GENES = [
    "EGFR","TP53","PTEN","IDH1","IDH2","BRAF","KRAS","PIK3CA",
    "RB1","CDKN2A","MYC","MYCN","ALK","PDGFRA","NF1","VHL",
]
_CANCER_CHEMBL_IDS = [
    "CHEMBL614","CHEMBL1201583","CHEMBL941","CHEMBL535","CHEMBL3788023",
    "CHEMBL25","CHEMBL1421","CHEMBL2068237",
]


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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("researcher")),
):
    """Trigger GDC/TCGA somatic mutation ETL for a TCGA project."""
    orch = ETLOrchestrator(db)
    job = await orch.create_job("gdc")
    run_etl_gdc.delay(job.id, project, gene_ids)
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
