"""Celery tasks for asynchronous ETL pipeline execution."""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from celery.exceptions import MaxRetriesExceededError
from celery_app import celery_app
from app.core.config import settings
from app.services.etl.orchestrator import ETLOrchestrator
from app.core.logging import logger
from app.core.metrics import ETL_JOBS
from typing import List


def _get_session():
    """
    Create a fresh engine with NullPool for every task invocation.
    Celery workers fork processes and inherit the asyncpg pool from the
    parent event loop — reusing those connections causes:
        InterfaceError: cannot perform operation: another operation is in progress
    NullPool creates a brand-new connection per task and closes it when done.
    """
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _run_task(source: str, orch_method: str, *args):
    """Run an async orchestrator method in a clean event loop."""
    async def _inner():
        SessionLocal = _get_session()
        async with SessionLocal() as db:
            orch = ETLOrchestrator(db)
            await getattr(orch, orch_method)(*args)

    asyncio.run(_inner())


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, name="etl.opentargets")
def run_etl_opentargets(self, job_id: int, efo_id: str):
    logger.info(f"[ETL] opentargets job={job_id}")
    try:
        _run_task("opentargets", "ingest_opentargets", job_id, efo_id)
        ETL_JOBS.labels("opentargets", "success").inc()
    except Exception as exc:
        ETL_JOBS.labels("opentargets", "failed").inc()
        logger.error(f"[ETL] opentargets job={job_id} failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            raise


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, name="etl.string")
def run_etl_string(self, job_id: int, gene_symbols: List[str], min_score: int = 700):
    logger.info(f"[ETL] string job={job_id}")
    try:
        _run_task("string", "ingest_string", job_id, gene_symbols, min_score)
        ETL_JOBS.labels("string", "success").inc()
    except Exception as exc:
        ETL_JOBS.labels("string", "failed").inc()
        logger.error(f"[ETL] string job={job_id} failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            raise


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, name="etl.dgidb")
def run_etl_dgidb(self, job_id: int, genes: List[str]):
    logger.info(f"[ETL] dgidb job={job_id}")
    try:
        _run_task("dgidb", "ingest_dgidb", job_id, genes)
        ETL_JOBS.labels("dgidb", "success").inc()
    except Exception as exc:
        ETL_JOBS.labels("dgidb", "failed").inc()
        logger.error(f"[ETL] dgidb job={job_id} failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            raise


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, name="etl.chembl")
def run_etl_chembl(self, job_id: int, chembl_ids: List[str]):
    logger.info(f"[ETL] chembl job={job_id}")
    try:
        _run_task("chembl", "ingest_chembl", job_id, chembl_ids)
        ETL_JOBS.labels("chembl", "success").inc()
    except Exception as exc:
        ETL_JOBS.labels("chembl", "failed").inc()
        logger.error(f"[ETL] chembl job={job_id} failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            raise


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, name="etl.uniprot")
def run_etl_uniprot(self, job_id: int, query: str, size: int = 50):
    logger.info(f"[ETL] uniprot job={job_id}")
    try:
        _run_task("uniprot", "ingest_uniprot", job_id, query, size)
        ETL_JOBS.labels("uniprot", "success").inc()
    except Exception as exc:
        ETL_JOBS.labels("uniprot", "failed").inc()
        logger.error(f"[ETL] uniprot job={job_id} failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            raise


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, name="etl.clinicaltrials")
def run_etl_clinicaltrials(self, job_id: int, condition: str, intervention: str = None):
    logger.info(f"[ETL] clinicaltrials job={job_id}")
    try:
        _run_task("clinicaltrials", "ingest_clinicaltrials", job_id, condition, intervention)
        ETL_JOBS.labels("clinicaltrials", "success").inc()
    except Exception as exc:
        ETL_JOBS.labels("clinicaltrials", "failed").inc()
        logger.error(f"[ETL] clinicaltrials job={job_id} failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            raise


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, name="etl.gdc")
def run_etl_gdc(self, job_id: int, project: str, gene_ids: List[str] = None,
                 min_co_occurrences: int = 2):
    logger.info(f"[ETL] gdc job={job_id}")
    try:
        _run_task("gdc", "ingest_gdc", job_id, project, gene_ids, min_co_occurrences)
        ETL_JOBS.labels("gdc", "success").inc()
    except Exception as exc:
        ETL_JOBS.labels("gdc", "failed").inc()
        logger.error(f"[ETL] gdc job={job_id} failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            raise
