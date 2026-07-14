import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.config import settings
from app.core.logging import logger


class StringClient:
    """
    STRING-db API client.
    Uses /network endpoint (more stable than /interaction_partners).
    Identifiers are sent newline-separated via POST form data.
    """
    BASE = "https://string-db.org/api"

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError)),
        reraise=True,
    )
    async def get_interaction_partners(self, identifiers: list, species: int = 9606, required_score: int = 700):
        """Fetch PPI network for a list of gene symbols."""
        # POST form-encoded; STRING expects newline-separated identifiers
        data = {
            "identifiers": "\n".join(identifiers),
            "species": str(species),
            "required_score": str(required_score),
            "caller_identity": "neurodrug_platform",
        }

        # Try /network first (stable endpoint), fall back to /interaction_partners
        for endpoint in ["/json/network", "/json/interaction_partners"]:
            try:
                resp = await self.client.post(
                    self.BASE + endpoint,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"STRING {endpoint} returned {resp.status_code}, trying next")
            except httpx.HTTPStatusError:
                continue

        # Last resort: GET with params
        params = {
            "identifiers": "%0d".join(identifiers),
            "species": species,
            "required_score": required_score,
            "caller_identity": "neurodrug_platform",
        }
        resp = await self.client.get(self.BASE + "/json/network", params=params)
        resp.raise_for_status()
        return resp.json()
