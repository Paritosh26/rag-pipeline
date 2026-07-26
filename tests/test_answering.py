from app.application.services.answer_service import AnswerService
from app.application.services.retrieval_service import RetrievalService
from app.config_util import Settings


class StubEmbeddingProvider:
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class StubVectorStore:
    def initialize(self) -> None:
        return None

    def upsert(self, chunks, embeddings) -> None:
        return None

    def search(self, query_embedding, top_k):
        return [
            type('Chunk', (), {'content': 'context snippet', 'source_id': 'doc-1', 'score': 0.95, 'metadata': {}})()
        ]


class StubLLMProvider:
    def generate(self, prompt: str) -> str:
        return 'stub answer'


class FailIfCalledLLMProvider:
    def generate(self, prompt: str) -> str:
        raise AssertionError('LLM provider should not have been called below the retrieval score threshold')


def test_answer_service_returns_structured_payload() -> None:
    retrieval_service = RetrievalService(
        embedding_provider=StubEmbeddingProvider(),
        vector_store=StubVectorStore(),
        top_k=3,
    )
    answer_service = AnswerService(retrieval_service=retrieval_service, llm_provider=StubLLMProvider())

    payload = answer_service.answer('What is this?')

    assert payload['answer'] == 'stub answer'
    assert payload['citations'][0]['source_id'] == 'doc-1'
    assert payload['citations'][0]['score'] == 0.95


def test_answer_service_falls_back_to_grounded_context_when_no_provider() -> None:
    retrieval_service = RetrievalService(
        embedding_provider=StubEmbeddingProvider(),
        vector_store=StubVectorStore(),
        top_k=3,
    )
    answer_service = AnswerService(retrieval_service=retrieval_service, llm_provider=None)

    payload = answer_service.answer('What is this?')

    assert payload['answer'].startswith('Based on the retrieved context')
    assert payload['citations'][0]['source_id'] == 'doc-1'
    assert payload['citations'][0]['excerpt'].startswith('context snippet')


def test_answer_service_skips_llm_call_below_retrieval_score_threshold() -> None:
    # StubVectorStore always returns a chunk with score 0.95.
    retrieval_service = RetrievalService(
        embedding_provider=StubEmbeddingProvider(),
        vector_store=StubVectorStore(),
        top_k=3,
    )
    settings = Settings(retrieval_score_threshold=0.99)
    answer_service = AnswerService(
        retrieval_service=retrieval_service,
        llm_provider=FailIfCalledLLMProvider(),
        settings=settings,
    )

    payload = answer_service.answer('What is this?')

    assert payload['answer'].startswith('Based on the retrieved context')


def test_answer_service_calls_llm_when_score_meets_threshold() -> None:
    retrieval_service = RetrievalService(
        embedding_provider=StubEmbeddingProvider(),
        vector_store=StubVectorStore(),
        top_k=3,
    )
    settings = Settings(retrieval_score_threshold=0.5)
    answer_service = AnswerService(
        retrieval_service=retrieval_service,
        llm_provider=StubLLMProvider(),
        settings=settings,
    )

    payload = answer_service.answer('What is this?')

    assert payload['answer'] == 'stub answer'
