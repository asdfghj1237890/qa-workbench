"""Real text embeddings over standard HTTP, with no synthetic fallback."""

from .http import (
    EmbeddingBatch,
    EmbeddingLimits,
    EmbeddingPricing,
    OpenAIEmbedding,
    TEIEmbedding,
)

__all__ = ["EmbeddingBatch", "EmbeddingLimits", "EmbeddingPricing", "OpenAIEmbedding", "TEIEmbedding"]
