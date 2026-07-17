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
    async def get_molecular_profiles(self, study_id: str) -> list:
        """List all molecular profiles for a study, so we can find the real
        mutation profile ID instead of guessing {study_id}_mutations."""
        url = f"{self.base_url}/studies/{study_id}/molecular-profiles"
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        reraise=True,
    )
    async def get_sample_lists(self, study_id: str) -> list:
        """List all sample lists for a study, so we can find the real
        'all samples' list ID instead of guessing {study_id}_all."""
        url = f"{self.base_url}/studies/{study_id}/sample-lists"
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()

    async def resolve_mutation_profile_and_sample_list(self, study_id: str) -> tuple:
        """
        FIX C12: get_mutations() used to assume every study names its
        default mutation profile '{study_id}_mutations' and its full
        sample list '{study_id}_all'. That convention doesn't hold for all
        studies (confirmed: es_dfarber_broad_2014 returned only 2 patients
        out of a 107-sample cohort under that guess — the wrong IDs matched
        almost nothing instead of erroring). This looks up the real IDs:
        the molecular profile whose molecularAlterationType is
        "MUTATION_EXTENDED", and the sample list with the largest sample
        count (typically the "all samples" list, but picking the largest
        rather than assuming a name is more robust across studies).
        """
        profiles = await self.get_molecular_profiles(study_id)
        mutation_profiles = [
            p for p in profiles
            if p.get("molecularAlterationType") == "MUTATION_EXTENDED"
        ]
        if not mutation_profiles:
            raise ValueError(
                f"No MUTATION_EXTENDED molecular profile found for study "
                f"'{study_id}'. Available profiles: "
                f"{[p.get('molecularProfileId') for p in profiles]}"
            )
        molecular_profile_id = mutation_profiles[0]["molecularProfileId"]

        sample_lists = await self.get_sample_lists(study_id)
        if not sample_lists:
            raise ValueError(f"No sample lists found for study '{study_id}'.")
        largest = max(sample_lists, key=lambda s: len(s.get("sampleIds", [])) or 0)
        sample_list_id = largest["sampleListId"]

        return molecular_profile_id, sample_list_id

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        reraise=True,
    )
    async def resolve_entrez_ids(self, gene_symbols: list) -> dict:
        """
        FIX C13: cBioPortal's GET .../mutations endpoint requires a single
        entrezGeneId and isn't meant for bulk study-wide fetches (confirmed:
        it 400s with "Request parameter is missing: entrezGeneId" when
        called without one). The correct way to fetch mutations for a gene
        panel is the POST .../mutations/fetch endpoint, which takes a list
        of Entrez Gene IDs — not Hugo symbols — so we resolve symbols here
        first. Returns {hugoGeneSymbol: entrezGeneId}.
        """
        url = f"{self.base_url}/genes/fetch"
        params = {"geneIdType": "HUGO_GENE_SYMBOL"}
        response = await self.client.post(url, params=params, json=gene_symbols)
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{response.status_code} error resolving gene symbols {gene_symbols}: {response.text[:500]}",
                request=response.request,
                response=response,
            )
        genes = response.json()
        return {g["hugoGeneSymbol"]: g["entrezGeneId"] for g in genes}

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        reraise=True,
    )
    async def get_mutations(self, study_id: str, gene_symbols: list,
                             molecular_profile_id: str = None,
                             sample_list_id: str = None) -> list:
        """
        Fetch mutation records for a specific gene panel via the documented
        POST .../mutations/fetch endpoint (see FIX C13). gene_symbols is
        required — this endpoint is not meant for unfiltered whole-study
        fetches; scope it to your driver gene panel.
        """
        if not gene_symbols:
            raise ValueError(
                "get_mutations requires gene_symbols — cBioPortal's mutation "
                "fetch endpoint needs explicit Entrez Gene IDs, it does not "
                "support an unfiltered whole-study fetch."
            )
        if not molecular_profile_id or not sample_list_id:
            molecular_profile_id, sample_list_id = await self.resolve_mutation_profile_and_sample_list(study_id)

        symbol_to_entrez = await self.resolve_entrez_ids(gene_symbols)
        missing = [s for s in gene_symbols if s not in symbol_to_entrez]
        if missing:
            raise ValueError(f"Could not resolve Entrez IDs for genes: {missing} — check spelling.")
        entrez_to_symbol = {v: k for k, v in symbol_to_entrez.items()}

        url = f"{self.base_url}/molecular-profiles/{molecular_profile_id}/mutations/fetch"
        params = {"projection": "DETAILED"}
        body = {
            "entrezGeneIds": list(symbol_to_entrez.values()),
            "sampleListId": sample_list_id,
        }
        response = await self.client.post(url, params=params, json=body)
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{response.status_code} error for {response.url}: {response.text[:500]}",
                request=response.request,
                response=response,
            )
        mutations = response.json()
        # DETAILED projection returns entrezGeneId under gene.entrezGeneId
        # but doesn't always echo hugoGeneSymbol reliably — attach it
        # ourselves from the resolved mapping so callers can rely on it.
        for mut in mutations:
            entrez_id = (mut.get("gene") or {}).get("entrezGeneId")
            if entrez_id in entrez_to_symbol:
                mut.setdefault("gene", {})["hugoGeneSymbol"] = entrez_to_symbol[entrez_id]
        return mutations

    async def get_structural_variants(self, study_id: str, gene_symbols: list) -> list:
        """
        FIX C14: gene FUSIONS (e.g. EWSR1-FLI1, the defining alteration in
        Ewing Sarcoma) are NOT point mutations/indels and do not show up
        via get_mutations()/the MUTATION_EXTENDED profile — cBioPortal
        stores them under a separate STRUCTURAL_VARIANT molecular profile
        and a dedicated /structural-variant/fetch endpoint (this was a
        breaking change in cBioPortal v5; older docs/examples referencing
        a "_fusion" profile suffix are stale). Confirms whether the study
        actually has SV data before assuming it does — many WES-only
        studies never uploaded fusion calls at all, since fusions are
        typically detected via RNA-seq or targeted assays, not WES.
        Returns [] with a clear reason if no SV profile exists, rather than
        silently returning nothing indistinguishable from "no fusions found".
        """
        profiles = await self.get_molecular_profiles(study_id)
        sv_profiles = [p for p in profiles if p.get("molecularAlterationType") == "STRUCTURAL_VARIANT"]
        if not sv_profiles:
            raise ValueError(
                f"Study '{study_id}' has no STRUCTURAL_VARIANT molecular profile — "
                f"it likely never had fusion/SV calls uploaded (common for "
                f"WES-only studies, since fusions are usually called from "
                f"RNA-seq or targeted assays, not exome sequencing). Available "
                f"profile types: {sorted(set(p.get('molecularAlterationType') for p in profiles))}"
            )
        sv_profile_id = sv_profiles[0]["molecularProfileId"]

        symbol_to_entrez = await self.resolve_entrez_ids(gene_symbols)
        entrez_to_symbol = {v: k for k, v in symbol_to_entrez.items()}

        url = f"{self.base_url}/structural-variant/fetch"
        body = {
            "entrezGeneIds": list(symbol_to_entrez.values()),
            "molecularProfileIds": [sv_profile_id],
        }
        response = await self.client.post(url, json=body)
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{response.status_code} error for {response.url}: {response.text[:500]}",
                request=response.request,
                response=response,
            )
        svs = response.json()
        return svs
