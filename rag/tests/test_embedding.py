import unittest
from types import SimpleNamespace

import numpy as np

from rag.src.embedding import GeminiEmbeddingModel


class FakeModels:
    def __init__(self):
        self.calls = []

    def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        count = len(kwargs["contents"])
        embeddings = [
            SimpleNamespace(values=[3.0, 4.0, 0.0, 0.0])
            for _ in range(count)
        ]
        return SimpleNamespace(embeddings=embeddings)


class GeminiEmbeddingModelTests(unittest.TestCase):
    def setUp(self):
        self.models = FakeModels()
        self.model = GeminiEmbeddingModel(
            client=SimpleNamespace(models=self.models),
            output_dimension=4,
            batch_size=2,
        )

    def test_query_embedding_uses_retrieval_query_and_normalizes(self):
        vector = self.model.encode("query: 시험 언제야")

        self.assertEqual(vector.shape, (4,))
        self.assertAlmostEqual(float(np.linalg.norm(vector)), 1.0)
        call = self.models.calls[0]
        self.assertEqual(call["contents"], ["시험 언제야"])
        self.assertEqual(call["config"].task_type, "RETRIEVAL_QUERY")
        self.assertEqual(call["config"].output_dimensionality, 4)

    def test_document_embeddings_are_batched(self):
        vectors = self.model.encode(
            ["passage: 하나", "passage: 둘", "passage: 셋"]
        )

        self.assertEqual(vectors.shape, (3, 4))
        self.assertEqual(len(self.models.calls), 2)
        self.assertTrue(
            all(
                call["config"].task_type == "RETRIEVAL_DOCUMENT"
                for call in self.models.calls
            )
        )

    def test_mixed_task_types_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "동일한 task type"):
            self.model.encode(["query: 질문", "passage: 공지"])


if __name__ == "__main__":
    unittest.main()
