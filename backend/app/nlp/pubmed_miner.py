import httpx
from typing import List, Dict, Any
from app.core.logging import logger


class PubMedMiner:
    def __init__(self):
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    async def search(self, query: str, max_results: int = 100) -> List[str]:
        url = f"{self.base_url}/esearch.fcgi"
        params = {"db": "pubmed", "term": query, "retmax": max_results, "retmode": "json"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("esearchresult", {}).get("idlist", [])

    async def fetch_summaries(self, pmids: List[str]) -> List[Dict[str, Any]]:
        if not pmids:
            return []
        url = f"{self.base_url}/esummary.fcgi"
        params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            result = data.get("result", {})
            summaries = []
            for pmid in pmids:
                info = result.get(pmid, {})
                summaries.append({
                    "pmid": pmid,
                    "title": info.get("title"),
                    "authors": [a.get("name") for a in info.get("authors", [])],
                    "journal": info.get("fulljournalname"),
                    "year": int(info.get("pubdate", "0")[:4]) if info.get("pubdate") else None,
                })
            return summaries
