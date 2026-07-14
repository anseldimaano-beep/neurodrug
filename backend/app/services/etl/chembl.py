import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.config import settings


class ChEMBLClient:
    def __init__(self):
        self.base_url = settings.CHEMBL_API
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
    async def get_molecule(self, chembl_id: str):
        url = f"{self.base_url}/molecule/{chembl_id}.json"
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()

    async def search_molecules(self, query: str, limit: int = 20):
        url = f"{self.base_url}/molecule.json"
        params = {"q": query, "limit": limit}
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()
