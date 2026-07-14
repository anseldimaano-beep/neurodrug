import re
from typing import List, Dict, Any


class EvidenceExtractor:
    DRUG_INDICATORS = ["treatment", "therapy", "inhibitor", "agonist", "antagonist", "modulator"]
    CLINICAL_INDICATORS = ["clinical trial", "phase", "patient", "cohort", "efficacy", "safety"]

    @staticmethod
    def extract_drug_mentions(text: str, drug_names: List[str]) -> Dict[str, int]:
        mentions = {}
        text_lower = text.lower()
        for drug in drug_names:
            count = len(re.findall(rf"\b{re.escape(drug.lower())}\b", text_lower))
            if count > 0:
                mentions[drug] = count
        return mentions

    @staticmethod
    def classify_evidence_level(text: str) -> str:
        text_lower = text.lower()
        if any(w in text_lower for w in EvidenceExtractor.CLINICAL_INDICATORS):
            return "level_1"
        if any(w in text_lower for w in EvidenceExtractor.DRUG_INDICATORS):
            return "level_2"
        return "level_3"
