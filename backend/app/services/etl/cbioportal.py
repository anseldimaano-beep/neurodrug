import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class CBioPortalClient:
    """
    Client for the public cBioPortal REST API (https://www.cbioportal.org/api).
    No authentication required for public-instance studies — this covers
    published, de-identified cohorts curated from the literature, including
    pediatric cancers that don't have a dedicated public GDC project (e.g.
    Ewing Sarcoma, Medulloblastoma).

    Unlike GDC, we don't hardcode a study_id here: cBioPortal's study IDs
    are per-publication (e.g. multiple independent Ewing Sarcoma cohorts may
    exist under different IDs) and can change as new studies are curated, so
    search_studies() is the intended way to resolve the current correct ID
    before calling get_mutations().
    """

    def __init__(self):
        self.base_url = "https://www.cbioportal.org/api"
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
    async def search_studies(self, keyword: str) -> list:
        """
        Search public studies by keyword (e.g. 'ewing sarcoma',
        'medulloblastoma'). Returns study summaries including studyId,
        name, and allSampleCount — inspect these to pick the right study_id
        before calling get_mutations(). Prefer larger, more recent cohorts
        when multiple studies match.
        """
        url = f"{self.base_url}/studies"
        params = {"keyword": keyword, "projection": "SUMMARY", "pageSize": 100}
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        reraise=True,
    )
    async def get_mutations(self, study_id: str, molecular_profile_suffix: str = "_mutations",
                             sample_list_suffix: str = "_all", page_size: int = 10000) -> list:
        """
        Fetch all mutation records for a study via the POST /fetch endpoint
        (cBioPortal has moved several query endpoints to POST+JSON body;
        the plain GET+querystring form returns 400 on the current API).
        """
        molecular_profile_id = f"{study_id}{molecular_profile_suffix}"
        sample_list_id = f"{study_id}{sample_list_suffix}"
        url = f"{self.base_url}/molecular-profiles/{molecular_profile_id}/mutations/fetch"
        params = {"projection": "DETAILED"}
        body = {"sampleListId": sample_list_id}
        response = await self.client.post(url, params=params, json=body)
        response.raise_for_status()
        return response.json()