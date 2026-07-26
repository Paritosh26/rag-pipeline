from __future__ import annotations

import logging

from app.application.services.retrieval_service import RetrievalService
from app.config_util import Settings, settings as default_settings
from app.llm.gemini_provider import LLMProvider

logger = logging.getLogger(__name__)


class AnswerService:
    """Generate grounded answers from retrieved context."""

    def __init__(
        self,
        retrieval_service: RetrievalService,
        llm_provider: LLMProvider | None = None,
        settings: Settings = default_settings,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.llm_provider = llm_provider
        self.settings = settings

    def answer(self, question: str) -> dict[str, object]:
        """Retrieve context and build a grounded answer payload."""
        chunks = self.retrieval_service.retrieve(question)
        context = '\n\n'.join(chunk.content for chunk in chunks)
        prompt = self.settings.prompt_template.format(context=context, question=question)
        top_score = max((chunk.score for chunk in chunks), default=0.0)
        below_threshold = top_score < self.settings.retrieval_score_threshold

        answer_text = None
        llm_error: str | None = None
        if below_threshold:
            logger.info(
                'Top retrieval score %.3f below retrieval_score_threshold %.3f; skipping LLM call for question %r',
                top_score, self.settings.retrieval_score_threshold, question,
            )
        elif self.llm_provider is not None:
            try:
                answer_text = self.llm_provider.generate(prompt)
                logger.info('Generated answer via %s for question %r', type(self.llm_provider).__name__, question)
            except Exception as exc:
                llm_error = f'{type(exc).__name__}: {exc}'
                logger.exception('LLM generation failed; falling back to extractive answer')
        else:
            logger.info('No LLM provider configured; using extractive fallback for question %r', question)

        degraded = answer_text is None
        if answer_text is None:
            answer_text = (
                'Based on the retrieved context, I can summarize that the most relevant evidence '
                f'points to: {context[:240]}'
            )

        return {
            'answer': answer_text,
            'answer_source': 'extractive' if degraded else 'llm',
            'citations': [
                {
                    'source_id': chunk.source_id,
                    'score': chunk.score,
                    'metadata': chunk.metadata,
                    'excerpt': chunk.content[:200],
                }
                for chunk in chunks
            ],
            'lineage': {
                'question': question,
                'collection': self.settings.collection_name,
                'retrieved_chunk_count': len(chunks),
                # Surfaced so callers can tell a real LLM answer from a
                # degraded extractive one instead of only seeing it in logs.
                'llm_error': llm_error,
            },
        }
