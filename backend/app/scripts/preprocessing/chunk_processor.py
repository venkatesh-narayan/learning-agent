import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

from app.models.recommendations.content_analysis import (
    Concept,
    ConceptRelationship,
    ContentAnalysis,
    ContentComplexity,
)
from app.models.topic_analysis import ThematicAnalysis, TopicAnalysis
from app.services.preprocessing.concept_extractor import ConceptExtractor
from app.services.preprocessing.content_chunker import ContentChunk, ContentChunker
from app.services.preprocessing.topic_analyzer import TopicAnalyzer
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ProcessedContent:
    """Full content analysis across all chunks."""

    content_analysis: ContentAnalysis
    topic_analysis: TopicAnalysis
    chunk_metadata: Dict[str, Any]  # Info about chunking process


class ChunkProcessor:
    """Coordinates chunking and analysis of content."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_concurrent: int = 10,  # Limit concurrent API calls
    ):
        self.chunker = ContentChunker()
        self.concept_extractor = ConceptExtractor(model=model)
        self.topic_analyzer = TopicAnalyzer(model=model)
        self.max_concurrent = max_concurrent

    async def split_content(
        self, content: Dict, content_type: str
    ) -> AsyncIterator[Optional[ProcessedContent]]:
        """Split content into sections based on content type."""

        if content_type == "sec_filing":
            texts = self._process_sec_filing(content)

        elif content_type == "news_article":
            texts = self._process_news_article(content)

        elif content_type == "financial_statements":
            texts = self._process_financial_statements(content)

        elif content_type == "company_details":
            texts = self._process_company_details(content)

        else:
            logger.error(f"Unsupported content type: {content_type}")
            raise ValueError(f"Unsupported content type: {content_type}")

        logger.info(f"Split {content_type} into {len(texts)} sections")
        for text in texts:
            yield await self.process_content(text)

    def _process_sec_filing(self, content: Dict) -> List[str]:
        html_content = content.get("filing_html", "")
        if not html_content:
            logger.info("No HTML content found in SEC filing")
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        for element in soup(["script", "style"]):
            element.decompose()

        return [soup.get_text(separator="\n", strip=True)]

    def _process_news_article(self, content: Dict) -> List[str]:
        return [
            f"Title: {content.get('title', '')}\n\n"
            f"Description: {content.get('description', '')}\n\n"
            f"{content.get('content', '')}"
        ]

    def _process_financial_statements(self, content: Dict) -> List[str]:
        results = content.get("results", [])
        if not results:
            logger.warning("No financial results found")
            return []

        financials = results[0].get("financials", {})
        texts = []

        for statement_type, statement_data in financials.items():
            statement_text = f"{statement_type.replace('_', ' ').title()}:\n\n"
            items = sorted(
                statement_data.items(),
                key=lambda x: (
                    x[1].get("order", 999) if isinstance(x[1], dict) else 999
                ),
            )

            for item_name, item_data in items:
                if not isinstance(item_data, dict):
                    continue

                value = item_data.get("value", 0)
                unit = item_data.get("unit", "USD")
                label = item_data.get("label", item_name.replace("_", " ").title())

                formatted_value = (
                    f"{value:,.2f}" if isinstance(value, (int, float)) else str(value)
                )
                statement_text += f"{label}: {formatted_value} {unit}\n"

            texts.append(statement_text)

        return texts

    def _process_company_details(self, content: Dict) -> List[str]:
        company_data = content.get("company_details", {})
        news_data = content.get("recent_news", [])

        texts = [
            f"Company: {company_data.get('name', '')}\n"
            f"Ticker: {company_data.get('ticker', '')}\n"
            f"Exchange: {company_data.get('primary_exchange', '')}\n"
            f"Industry: {company_data.get('sic_description', '')}\n"
        ]

        if news_data:
            for news_item in news_data:
                news_text = (
                    f"Title: {news_item.get('title', '')}\n"
                    f"Date: {news_item.get('published_utc', '')}\n"
                    f"Author: {news_item.get('author', '')}\n"
                    f"Publisher: {news_item.get('publisher', {}).get('name', '')}\n\n"
                    f"{news_item.get('description', '')}"
                )
                texts.append(news_text)

        return texts

    async def process_content(self, text: str) -> Optional[ProcessedContent]:
        """
        Process content end-to-end:
        1. Split into appropriate chunks
        2. Analyze each chunk
        3. Combine results intelligently
        """
        # First chunk the content
        chunks = self.chunker.chunk_content(text)

        # Process chunks in parallel with rate limiting
        semaphore = asyncio.Semaphore(self.max_concurrent)
        tasks = []

        async def process_chunk(chunk: ContentChunk):
            async with semaphore:
                concept_analysis = await self.concept_extractor.extract_concepts(
                    chunk.text
                )
                topic_analysis = await self.topic_analyzer.analyze_topics(chunk.text)
                return {
                    "chunk": chunk,
                    "concepts": concept_analysis,
                    "topics": topic_analysis,
                }

        for chunk in chunks:
            tasks.append(asyncio.create_task(process_chunk(chunk)))

        chunk_results = await asyncio.gather(*tasks)

        # Combine results from all chunks
        combined_content = self._combine_content_analyses(
            [r["concepts"] for r in chunk_results], [r["chunk"] for r in chunk_results]
        )
        if not combined_content:
            return None

        combined_topics = self._combine_topic_analyses(
            [r["topics"] for r in chunk_results]
        )
        if not combined_topics:
            return None

        # Create chunk metadata
        metadata = {
            "num_chunks": len(chunks),
            "chunk_sizes": [len(c.text) for c in chunks],
            "processing_stats": self._get_processing_stats(chunk_results),
        }

        return ProcessedContent(
            content_analysis=combined_content,
            topic_analysis=combined_topics,
            chunk_metadata=metadata,
        )

    def _combine_content_analyses(
        self, analyses: List[ContentAnalysis], chunks: List[ContentChunk]
    ) -> ContentAnalysis:
        """
        Intelligently combine concept analyses from multiple chunks:
        - Merge similar concepts
        - Resolve conflicts
        - Preserve context
        """
        all_main_concepts = []
        all_related_concepts = []
        all_relationships = []
        all_prerequisites = set()

        found_main_concepts = sum(1 for a in analyses if len(a.main_concepts) > 0)
        if found_main_concepts == 0:
            raise ValueError("No main concepts found in any chunk")

        # Track concept positions for better merging
        concept_positions = defaultdict(list)

        for analysis, chunk in zip(analyses, chunks):
            # Track where concepts appear
            for concept in analysis.main_concepts:
                concept_positions[concept.name].append(chunk.start_index)

            all_main_concepts.extend(analysis.main_concepts)
            all_related_concepts.extend(analysis.related_concepts)
            all_relationships.extend(analysis.relationships)
            all_prerequisites.update(analysis.prerequisites)

        # Merge similar concepts using position information
        merged_main_concepts = self._merge_similar_concepts(
            all_main_concepts, concept_positions
        )

        # Merge relationships
        merged_relationships = self._merge_relationships(all_relationships)

        # Create overall complexity score
        overall_complexity = self._combine_complexity_scores(analyses)

        return ContentAnalysis(
            main_concepts=merged_main_concepts,
            related_concepts=self._merge_similar_concepts(all_related_concepts, {}),
            relationships=merged_relationships,
            prerequisites=list(all_prerequisites),
            complexity=overall_complexity,
        )

    def _combine_topic_analyses(self, analyses: List[TopicAnalysis]) -> TopicAnalysis:
        """
        Combine topic analyses from chunks:
        - Identify main topic thread
        - Merge subtopics
        - Combine theme analysis
        """
        # Count topic occurrences for primary topic selection
        topic_counts = {}
        for analysis in analyses:
            topic_name = analysis.primary_topic.name
            if topic_name not in topic_counts:
                topic_counts[topic_name] = {
                    "count": 0,
                    "topic": analysis.primary_topic,
                }
            topic_counts[topic_name]["count"] += 1

        # Select most common topic as primary
        primary_topic = max(topic_counts.values(), key=lambda x: x["count"])["topic"]

        # Merge secondary topics
        all_secondary = []
        seen_topics = {primary_topic.name}

        for analysis in analyses:
            for topic in analysis.secondary_topics:
                if topic.name not in seen_topics:
                    all_secondary.append(topic)
                    seen_topics.add(topic.name)

        # Combine theme analyses
        combined_themes = self._merge_thematic_analyses([a.themes for a in analyses])

        return TopicAnalysis(
            primary_topic=primary_topic,
            secondary_topics=all_secondary,
            themes=combined_themes,
            content_focus=self._determine_content_focus(analyses),
        )

    def _merge_similar_concepts(
        self, concepts: List[Concept], positions: Dict[str, List[int]]
    ) -> List[Concept]:
        """Merge similar concepts using position information."""
        merged = []
        seen = set()

        # Sort concepts by earliest appearance if position info available
        def get_first_position(concept):
            return min(positions.get(concept.name, [float("inf")]))

        sorted_concepts = sorted(concepts, key=get_first_position)

        for concept in sorted_concepts:
            if concept.name not in seen:
                # Find similar concepts
                similar = [
                    c for c in concepts if self._are_concepts_similar(concept, c)
                ]

                # Merge metrics and definitions
                merged_concept = concept
                if len(similar) > 1:
                    merged_concept = self._merge_concept_info(similar)

                merged.append(merged_concept)
                seen.add(concept.name)

        return merged

    def _merge_relationships(
        self, relationships: List[ConceptRelationship]
    ) -> List[ConceptRelationship]:
        """Merge and deduplicate relationships."""
        merged = []
        seen = set()

        for rel in relationships:
            key = (rel.source, rel.target, rel.relationship)
            if key not in seen:
                merged.append(rel)
                seen.add(key)

        return merged

    def _combine_complexity_scores(
        self, analyses: List[ContentAnalysis]
    ) -> ContentComplexity:
        """Combine complexity analyses from chunks."""
        all_technical_terms = set()
        all_required = set()
        scores = []

        for analysis in analyses:
            scores.append(analysis.complexity.score)
            all_technical_terms.update(analysis.complexity.technical_terms)
            all_required.update(analysis.complexity.required_knowledge)

        return ContentComplexity(
            score=sum(scores) / len(scores),
            technical_terms=list(all_technical_terms),
            required_knowledge=list(all_required),
            reasoning="Combined from chunk analyses",
        )

    def _merge_thematic_analyses(
        self, theme_analyses: List[ThematicAnalysis]
    ) -> ThematicAnalysis:
        """Merge thematic analyses from chunks."""
        all_themes = set()
        all_evidence = []

        for analysis in theme_analyses:
            all_themes.update(analysis.main_themes)
            all_evidence.extend(analysis.supporting_evidence)

        return ThematicAnalysis(
            main_themes=list(all_themes),
            supporting_evidence=all_evidence,
            trend_analysis=self._combine_trend_analyses(theme_analyses),
        )

    def _determine_content_focus(self, analyses: List[TopicAnalysis]) -> str:
        """Determine overall content focus from chunk analyses."""
        focus_counts = {"broad": 0, "specific": 0}

        for analysis in analyses:
            if "broad" in analysis.content_focus.lower():
                focus_counts["broad"] += 1
            elif "specific" in analysis.content_focus.lower():
                focus_counts["specific"] += 1

        return (
            "broad" if focus_counts["broad"] > focus_counts["specific"] else "specific"
        )

    def _get_processing_stats(self, results: List[Dict]) -> Dict:
        """Get statistics about the processing of chunks."""
        return {
            "concepts_per_chunk": [len(r["concepts"].main_concepts) for r in results],
            "topics_per_chunk": [
                len(r["topics"].secondary_topics) + 1 for r in results
            ],
            "complexity_scores": [r["concepts"].complexity.score for r in results],
        }

    def _are_concepts_similar(self, c1: Concept, c2: Concept) -> bool:
        """Check if two concepts are similar enough to merge."""
        # Simple name similarity for now
        # Could be enhanced with embedding similarity
        return (
            c1.name.lower() == c2.name.lower()
            or c1.name.lower() in c2.name.lower()
            or c2.name.lower() in c1.name.lower()
        )

    def _merge_concept_info(self, similar_concepts: List[Concept]) -> Concept:
        """Merge information from similar concepts."""
        # Use the first concept as base
        base = similar_concepts[0].model_copy(deep=True)

        # Merge metrics
        all_metrics = set()
        for concept in similar_concepts:
            all_metrics.update(concept.metrics)

        base.metrics = list(all_metrics)

        return base

    def _combine_trend_analyses(self, analyses: List[ThematicAnalysis]) -> str:
        """Combine trend analyses into overall analysis."""
        # Simple concatenation for now
        # Could be enhanced with more sophisticated merging
        unique_trends = set()
        for analysis in analyses:
            unique_trends.add(analysis.trend_analysis)

        return "; ".join(unique_trends)

    async def close(self):
        """Cleanup resources."""
        await self.concept_extractor.close()
        await self.topic_analyzer.close()
