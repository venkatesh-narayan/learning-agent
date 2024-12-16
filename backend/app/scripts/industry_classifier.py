import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import spacy
import yaml

logger = logging.getLogger(__name__)


class IndustryClassifier:
    """GICS-based industry classification using NLP."""

    def __init__(self, gics_path: str = "taxonomies/gics.yaml"):
        self.nlp = spacy.load("en_core_web_lg")

        # Load GICS taxonomy
        with open(Path(__file__).parent / gics_path) as f:
            self.gics = yaml.safe_load(f)

        # Build industry vectors
        self.industry_vectors = {}
        self._build_industry_vectors()

    def _build_industry_vectors(self):
        """Pre-compute vectors for industry descriptions."""
        for sector, industries in self.gics.items():
            for industry, subsectors in industries.items():
                # Combine all subsector descriptions
                description = f"{sector} {industry} " + " ".join(
                    [s for s in subsectors]
                )
                doc = self.nlp(description.lower())
                if doc.has_vector:
                    key = f"{sector}/{industry}"
                    self.industry_vectors[key] = doc.vector

    def classify_text(
        self, text: str, min_confidence: float = 0.6, max_industries: int = 3
    ) -> List[Dict]:
        """
        Classify text into GICS industries.

        Returns:
        [
            {
                "sector": str,
                "industry": str,
                "confidence": float,
                "evidence": List[Dict]
            },
            ...
        ]
        """
        doc = self.nlp(text)
        industry_scores = defaultdict(lambda: {"score": 0.0, "evidence": []})

        # Process each sentence for context
        for sent in doc.sents:
            sent_vector = sent.vector

            # Compare with industry vectors
            for industry_path, industry_vector in self.industry_vectors.items():
                similarity = sent_vector.dot(industry_vector) / (
                    sent_vector.norm() * industry_vector.norm()
                )

                if similarity >= min_confidence:
                    sector, industry = industry_path.split("/")

                    # Update running score
                    current = industry_scores[industry_path]
                    current["score"] = max(current["score"], similarity)

                    # Store evidence if it's a strong match
                    if len(current["evidence"]) < 3:  # Limit evidence per industry
                        current["evidence"].append(
                            {"text": sent.text, "similarity": float(similarity)}
                        )

        # Prepare results
        results = []
        for industry_path, data in sorted(
            industry_scores.items(), key=lambda x: x[1]["score"], reverse=True
        )[:max_industries]:
            sector, industry = industry_path.split("/")
            results.append(
                {
                    "sector": sector,
                    "industry": industry,
                    "confidence": float(data["score"]),
                    "evidence": data["evidence"],
                }
            )

        return results

    def get_main_industry(self, text: str) -> Optional[Dict]:
        """Get the main industry classification."""
        classifications = self.classify_text(text, max_industries=1)
        return classifications[0] if classifications else None
