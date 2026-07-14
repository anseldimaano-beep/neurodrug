import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.config import settings


class ClinicalTrialsClient:
    def __init__(self):
        self.base_url = settings.CLINICAL_TRIALS_API
        self.client = httpx.AsyncClient(timeout=30.0)

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
    async def search_trials(self, condition: str, intervention: str = None, page_size: int = 100):
        url = f"{self.base_url}/studies"
        params = {
            "query.cond": condition,
            "pageSize": page_size,
            "format": "json",
        }
        if intervention:
            params["query.intr"] = intervention

        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()
