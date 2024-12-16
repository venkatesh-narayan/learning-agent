import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import spacy
import yaml

logger = logging.getLogger(__name__)


class FinancialConceptExtractor:
    """Extract financial concepts from text using a structured taxonomy."""

    def __init__(self, taxonomy_path: str = "taxonomies/financial_concepts.yaml"):
        self.nlp = spacy.load("en_core_web_lg")

        # Load taxonomy
        with open(Path(__file__).parent / taxonomy_path) as f:
            self.taxonomy = yaml.safe_load(f)

        # Build concept vectors for efficient matching
        self.concept_vectors = {}
        self._build_concept_vectors()

    def _build_concept_vectors(self):
        """Pre-compute vectors for all concepts in taxonomy."""
        for category, subcategories in self.taxonomy.items():
            for subcategory, concepts in subcategories.items():
                for concept in concepts:
                    doc = self.nlp(concept.lower())
                    if doc.has_vector:
                        key = f"{category}/{subcategory}/{concept}"
                        self.concept_vectors[key] = doc.vector

    def extract_concepts(
        self, text: str, min_similarity: float = 0.6
    ) -> Dict[str, List[Dict]]:
        """
        Extract financial concepts from text.

        Returns:
        {
            "category/subcategory": [
                {
                    "concept": str,
                    "context": str,
                    "similarity": float,
                    "span": (int, int)
                },
                ...
            ]
        }
        """
        doc = self.nlp(text)
        concepts = defaultdict(list)

        # Process each sentence for better context
        for sent in doc.sents:
            # Get noun phrases and named entities
            phrases = list(sent.noun_chunks) + list(sent.ents)

            for phrase in phrases:
                if not phrase.root.has_vector:
                    continue

                # Compare with concept vectors
                for concept_path, concept_vector in self.concept_vectors.items():
                    similarity = phrase.root.vector.dot(concept_vector) / (
                        phrase.root.vector_norm * concept_vector.norm()
                    )

                    if similarity >= min_similarity:
                        category, subcategory, concept = concept_path.split("/")
                        key = f"{category}/{subcategory}"

                        concepts[key].append(
                            {
                                "concept": concept,
                                "context": sent.text,
                                "similarity": float(similarity),
                                "span": (phrase.start_char, phrase.end_char),
                            }
                        )

        return dict(concepts)

    def get_main_concepts(self, text: str, max_concepts: int = 5) -> List[str]:
        """Get main concepts mentioned in text."""
        all_concepts = self.extract_concepts(text)

        # Flatten and sort by similarity
        concept_list = []
        for category_concepts in all_concepts.values():
            concept_list.extend(category_concepts)

        concept_list.sort(key=lambda x: x["similarity"], reverse=True)

        # Return unique concepts
        seen = set()
        main_concepts = []
        for concept in concept_list:
            if concept["concept"] not in seen and len(main_concepts) < max_concepts:
                seen.add(concept["concept"])
                main_concepts.append(concept["concept"])

        return main_concepts
