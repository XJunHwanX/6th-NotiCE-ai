"""Gemini embedding adapter shared by the chatbot and crawler pipeline."""

from __future__ import annotations

from typing import Any

import numpy as np
from google.genai import types

from .config import EMBEDDING_DIMENSION, GEMINI_EMBEDDING_MODEL_NAME
from .llm import get_client


QUERY_PREFIX = "query: "
DOCUMENT_PREFIX = "passage: "


class GeminiEmbeddingModel:
    """SentenceTransformer-compatible subset backed by Gemini Embedding API."""

    def __init__(
        self,
        client: Any | None = None,
        model_name: str = GEMINI_EMBEDDING_MODEL_NAME,
        output_dimension: int = EMBEDDING_DIMENSION,
        batch_size: int = 16,
    ) -> None:
        self.client = client or get_client()
        self.model_name = model_name
        self.output_dimension = output_dimension
        self.batch_size = batch_size

    @staticmethod
    def _prepare_text(text: str) -> tuple[str, str]:
        if text.startswith(QUERY_PREFIX):
            return text.removeprefix(QUERY_PREFIX), "RETRIEVAL_QUERY"
        if text.startswith(DOCUMENT_PREFIX):
            return text.removeprefix(DOCUMENT_PREFIX), "RETRIEVAL_DOCUMENT"
        return text, "SEMANTIC_SIMILARITY"

    def encode(
        self,
        sentences: str | list[str],
        batch_size: int | None = None,
        normalize_embeddings: bool = True,
        **_: Any,
    ) -> np.ndarray:
        single_input = isinstance(sentences, str)
        raw_texts = [sentences] if single_input else list(sentences)
        if not raw_texts:
            return np.empty((0, self.output_dimension), dtype=np.float32)

        prepared = [self._prepare_text(str(text)) for text in raw_texts]
        task_types = {task_type for _, task_type in prepared}
        if len(task_types) != 1:
            raise ValueError("한 임베딩 배치에는 동일한 task type만 사용할 수 있습니다.")

        task_type = prepared[0][1]
        texts = [text for text, _ in prepared]
        vectors: list[list[float]] = []
        request_batch_size = batch_size or self.batch_size

        for start in range(0, len(texts), request_batch_size):
            response = self.client.models.embed_content(
                model=self.model_name,
                contents=texts[start : start + request_batch_size],
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self.output_dimension,
                ),
            )
            embeddings = response.embeddings or []
            vectors.extend(list(embedding.values or []) for embedding in embeddings)

        array = np.asarray(vectors, dtype=np.float32)
        expected_shape = (len(texts), self.output_dimension)
        if array.shape != expected_shape:
            raise ValueError(
                "Gemini 임베딩 응답 차원이 올바르지 않습니다: "
                f"expected={expected_shape}, actual={array.shape}"
            )

        # Reduced-dimension Gemini embeddings must be normalized explicitly.
        if normalize_embeddings:
            norms = np.linalg.norm(array, axis=1, keepdims=True)
            if np.any(norms == 0):
                raise ValueError("Gemini가 크기가 0인 임베딩을 반환했습니다.")
            array = array / norms

        return array[0] if single_input else array
