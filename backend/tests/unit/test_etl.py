import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestETLOrchestrator:
    @pytest.mark.asyncio
    async def test_create_job(self, db_session):
        from app.services.etl.orchestrator import ETLOrchestrator
        orch = ETLOrchestrator(db_session)
        job = await orch.create_job("opentargets")
        assert job.id is not None
        assert job.source_name == "opentargets"
        assert job.status == "queued"

    def test_evidence_extractor_classify_clinical(self):
        from app.nlp.evidence_extractor import EvidenceExtractor
        text = "A randomized clinical trial showed patient response to treatment in phase 3."
        level = EvidenceExtractor.classify_evidence_level(text)
        assert level == "level_1"

    def test_evidence_extractor_drug_level(self):
        from app.nlp.evidence_extractor import EvidenceExtractor
        text = "The inhibitor showed strong binding affinity to the target receptor."
        level = EvidenceExtractor.classify_evidence_level(text)
        assert level == "level_2"

    def test_drug_mentions_extraction(self):
        from app.nlp.evidence_extractor import EvidenceExtractor
        text = "Imatinib and temozolomide were studied in this report. Imatinib was most effective."
        mentions = EvidenceExtractor.extract_drug_mentions(text, ["imatinib", "temozolomide", "bevacizumab"])
        assert mentions.get("imatinib") == 2
        assert mentions.get("temozolomide") == 1
        assert "bevacizumab" not in mentions
