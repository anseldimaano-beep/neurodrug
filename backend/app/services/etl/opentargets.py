import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from app.core.config import settings
from app.core.logging import logger


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError))


class OpenTargetsClient:
    def __init__(self):
        self.url = settings.OPEN_TARGETS_API
        self.client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=10))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    async def _query(self, query: str, variables: dict = None):
        payload = {"query": query, "variables": variables or {}}
        response = await self.client.post(
            self.url, json=payload, headers={"Content-Type": "application/json"}
        )
        if not response.is_success:
            logger.error(f"[OpenTargets] HTTP {response.status_code}: {response.text[:500]}")
            response.raise_for_status()
        data = response.json()
        if "errors" in data:
            logger.error(f"[OpenTargets] GraphQL errors: {data['errors']}")
            raise ValueError(f"GraphQL errors: {data['errors']}")
        return data["data"]

    async def get_disease_associations(self, efo_id: str):
        query = """
        query DiseaseAssociations($efoId: String!) {
          disease(efoId: $efoId) {
            associatedTargets(page: {index: 0, size: 200}) {
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
        result = await self._query(query, {"efoId": efo_id})
        if result is None:
            logger.warning(f"[OpenTargets] null result for {efo_id}")
            return []
        disease_data = result.get("disease")
        if disease_data is None:
            logger.warning(f"[OpenTargets] no disease found for {efo_id}")
            return []
        rows = (disease_data.get("associatedTargets") or {}).get("rows", []) or []
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