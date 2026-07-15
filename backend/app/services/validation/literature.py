import httpx
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.domain import Prediction, LiteratureEvidence
from app.core.logging import logger


class LiteratureValidationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    async def validate_prediction(self, prediction_id: int) -> List[LiteratureEvidence]:
        pred_result = await self.db.execute(
            select(Prediction)
            .options(
                selectinload(Prediction.drug),
                selectinload(Prediction.disease),
            )
            .where(Prediction.id == prediction_id)
        )
        prediction = pred_result.scalar_one_or_none()
        if not prediction or not prediction.drug or not prediction.disease:
            return []

        query = f'("{prediction.drug.name}"[Title/Abstract] AND "{prediction.disease.name}"[Title/Abstract])'
        pmids = await self._search_pubmed(query)

        # FIX C11: validate_prediction() used to insert a fresh row every
        # time it ran, even for a PMID it already had on file — repeated
        # "Validate" clicks silently duplicated rows in literature_evidence.
        # Skip PMIDs we've already stored for this prediction.
        existing_result = await self.db.execute(
            select(LiteratureEvidence.pubmed_id).where(
                LiteratureEvidence.prediction_id == prediction_id
            )
        )
        existing_pmids = {row[0] for row in existing_result.all()}
        new_pmids = [p for p in pmids[:10] if p not in existing_pmids]

        # FIX C7: fetching one esummary per PMID (up to 10 sequential NCBI
        # calls per prediction) blows past NCBI's ~3 req/sec limit once
        # "Validate All" runs across many predictions back-to-back, causing
        # 429s that killed the entire /validation/run request for that row.
        # esummary supports comma-separated ids in a single call — batch it.
        articles = await self._fetch_articles(new_pmids)

        new_evidences = []
        for pmid, article in articles.items():
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
            new_evidences.append(ev)

        # Return the FULL set (existing + newly added), not just what was
        # inserted this call, so the /run response reflects everything on
        # file for this prediction.
        if new_pmids or existing_pmids:
            existing_evidences_result = await self.db.execute(
                select(LiteratureEvidence).where(
                    LiteratureEvidence.prediction_id == prediction_id,
                    LiteratureEvidence.pubmed_id.in_(existing_pmids),
                )
            )
            evidences = list(existing_evidences_result.scalars().all()) + new_evidences
        else:
            evidences = new_evidences

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

    async def _fetch_articles(self, pmids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch-fetch article summaries for multiple PMIDs in a single
        esummary call, instead of one HTTP round-trip per PMID."""
        if not pmids:
            return {}
        url = f"{self.base_url}/esummary.fcgi"
        params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("result", {})

        out: Dict[str, Optional[Dict[str, Any]]] = {}
        for pmid in pmids:
            result = results.get(pmid)
            if not result:
                out[pmid] = None
                continue
            authors = [a.get("name") for a in result.get("authors", [])]
            out[pmid] = {
                "title": result.get("title"),
                "authors": authors,
                "journal": result.get("fulljournalname"),
                "year": int(result.get("pubdate", "0")[:4]) if result.get("pubdate") else None,
                "has_abstract": bool(result.get("hasabstract")),
            }
        return out
