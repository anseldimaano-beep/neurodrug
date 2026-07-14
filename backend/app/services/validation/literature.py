import httpx
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.domain import Prediction, LiteratureEvidence
from app.core.config import settings
from app.core.logging import logger


class LiteratureValidationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    async def validate_prediction(self, prediction_id: int) -> List[LiteratureEvidence]:
        pred_result = await self.db.execute(
            select(Prediction).where(Prediction.id == prediction_id)
        )
        prediction = pred_result.scalar_one_or_none()
        if not prediction or not prediction.drug or not prediction.disease:
            return []

        query = f'("{prediction.drug.name}"[Title/Abstract] AND "{prediction.disease.name}"[Title/Abstract])'
        pmids = await self._search_pubmed(query)

        evidences = []
        for pmid in pmids[:10]:
            article = await self._fetch_article(pmid)
            if not article:
                continue
            ev = LiteratureEvidence(
                prediction_id=prediction_id,
                pubmed_id=pmid,
                title=article.get("title"),
                authors=article.get("authors", []),
                journal=article.get("journal"),
                publication_year=article.get("year"),
                evidence_level="level_2" if article.get("has_abstract") else "level_3",
                supporting_text=article.get("abstract", "")[:2000],
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            )
            self.db.add(ev)
            evidences.append(ev)

        if evidences:
            prediction.status = "validated"
            prediction.evidence_score = len(evidences) / 10.0
        else:
            prediction.status = "novel"

        await self.db.commit()
        logger.info(f"Literature validation for prediction {prediction_id}: {len(evidences)} articles found")
        return evidences

    async def _search_pubmed(self, query: str, retmax: int = 20) -> List[str]:
        url = f"{self.base_url}/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": retmax,
            "retmode": "json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("esearchresult", {}).get("idlist", [])

    async def _fetch_article(self, pmid: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/esummary.fcgi"
        params = {"db": "pubmed", "id": pmid, "retmode": "json"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            result = data.get("result", {}).get(pmid, {})
            if not result:
                return None
            authors = [a.get("name") for a in result.get("authors", [])]
            return {
                "title": result.get("title"),
                "authors": authors,
                "journal": result.get("fulljournalname"),
                "year": int(result.get("pubdate", "0")[:4]) if result.get("pubdate") else None,
                "has_abstract": bool(result.get("hasabstract")),
            }
