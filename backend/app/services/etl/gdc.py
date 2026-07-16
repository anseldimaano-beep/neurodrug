import httpx
import json
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.config import settings


class GDCClient:
    def __init__(self):
        self.base_url = settings.GDC_API
        self.client = httpx.AsyncClient(timeout=60.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        reraise=True,
    )
    async def query_ssms(self, project: str, gene_ids: list = None, size: int = 1000):
        url = f"{self.base_url}/ssms"
        filters = {
            "op": "and",
            "content": [
                {"op": "=", "content": {"field": "occurrence.case.project.project_id", "value": project}}
            ],
        }
        if gene_ids:
            # FIX C11: this used to filter on
            # consequence.transcript.gene.gene_id, which GDC's schema
            # defines as the Ensembl gene ID (e.g. ENSG00000146648) — not
            # the gene symbol every other caller in this codebase passes
            # (e.g. "EGFR"). Filtering symbols against an Ensembl-ID field
            # silently matched zero records. Use .symbol, matching the
            # field this method already reads mutations back out with.
            filters["content"].append(
                {"op": "in", "content": {"field": "consequence.transcript.gene.symbol", "value": gene_ids}}
            )

        params = {
            "filters": json.dumps(filters),
            "size": size,
            "format": "JSON",
            "fields": (
                "genomic_dna_change,mutation_type,"
                "consequence.transcript.gene.symbol,"
                "occurrence.case.project.project_id,"
                "occurrence.case.case_id"
            ),
        }
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()
