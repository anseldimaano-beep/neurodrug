import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.config import settings
from app.core.logging import logger


class OpenTargetsClient:
    def __init__(self):
        self.url = settings.OPEN_TARGETS_API
        self.client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=10))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError)),
        reraise=True,
    )
    async def _query(self, query: str, variables: dict = None):
        payload = {"query": query, "variables": variables or {}}
        response = await self.client.post(
            self.url, json=payload, headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            raise ValueError(f"GraphQL errors: {data['errors']}")
        return data["data"]

    async def get_disease_associations(self, efo_id: str, size: int = 500):
        query = """
        query DiseaseAssociations($efoId: String!, $size: Int!) {
          disease(efoId: $efoId) {
            associatedTargets(page: {index: 0, size: $size}) {
              rows {
                target {
                  id
                  approvedSymbol
                  approvedName
                  biotype
                }
                score
              }
            }
          }
        }
        """
        result = await self._query(query, {"efoId": efo_id, "size": size})
        rows = result.get("disease", {}).get("associatedTargets", {}).get("rows", [])
        associations = []
        for row in rows:
            target = row.get("target", {})
            associations.append({
                "gene_symbol": target.get("approvedSymbol"),
                "gene_id": target.get("id"),
                "gene_name": target.get("approvedName"),
                "biotype": target.get("biotype"),
                "association_score": row.get("score"),
                "evidence_scores": {},
            })
        return associations
