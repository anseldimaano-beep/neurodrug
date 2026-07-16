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
        Fetch all mutation records for a study. Most cBioPortal studies
        follow the {study_id}_mutations / {study_id}_all naming convention
        for their default molecular profile and sample list — verify these
        exist for a given study via /api/studies/{study_id}/molecular-profiles
        if this returns a 404, since a small number of studies deviate.
        """
        molecular_profile_id = f"{study_id}{molecular_profile_suffix}"
        sample_list_id = f"{study_id}{sample_list_suffix}"
        url = f"{self.base_url}/molecular-profiles/{molecular_profile_id}/mutations"
        params = {
            "sampleListId": sample_list_id,
            "projection": "DETAILED",
            "pageNumber": 0,
            "pageSize": page_size,
            "direction": "ASC",
        }
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()