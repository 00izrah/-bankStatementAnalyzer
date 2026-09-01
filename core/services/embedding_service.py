"""
Embedding Service for Bank Statement Analyzer.

Singleton-loaded SentenceTransformer model that generates dense vector
embeddings for transaction descriptions. Used by the vector store and
copilot service for semantic search and retrieval.
"""
import logging
import numpy as np
from typing import List

from django.conf import settings

logger = logging.getLogger('bankstatements')

# Module-level singleton — the model is heavy (~80 MB) so we load it once
_model = None


def _get_model():
    """Lazy-load the SentenceTransformer model on first use."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL_NAME}")
            _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
            logger.info("Embedding model loaded successfully.")
        except ImportError:
            logger.error(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    return _model


class EmbeddingService:
    """
    Generates vector embeddings for transaction text representations.

    Usage:
        service = EmbeddingService()
        vectors = service.embed_texts(["POS SHOPRITE LEKKI", "UBER BV TRIP"])
        query_vec = service.embed_query("grocery shopping")
    """

    def __init__(self):
        self.model = _get_model()
        self.dimension = settings.EMBEDDING_DIMENSION

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """
        Encode a batch of text strings into dense vectors.

        Args:
            texts: List of transaction text representations.

        Returns:
            np.ndarray of shape (len(texts), self.dimension), dtype float32.
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        embeddings = self.model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,  # Unit-normalize for cosine similarity
        )
        return embeddings.astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """
        Encode a single query string into a dense vector.

        Returns:
            np.ndarray of shape (1, self.dimension), dtype float32.
        """
        return self.embed_texts([query])

    @staticmethod
    def build_transaction_text(
        date, description, amount, category_name=None, notes=""
    ) -> str:
        """
        Build a rich text representation of a transaction for embedding.

        This produces a structured string that captures the semantic meaning
        of the transaction better than raw bank memo text alone.

        Example output:
            "Date: 2024-01-15 | Memo: POS SHOPRITE LEKKI | Amount: ₦34,500.00 Debit | Category: Food & Dining"
        """
        direction = "Credit" if float(amount) > 0 else "Debit"
        abs_amount = abs(float(amount))
        parts = [
            f"Date: {date}",
            f"Memo: {description}",
            f"Amount: ₦{abs_amount:,.2f} {direction}",
        ]
        if category_name:
            parts.append(f"Category: {category_name}")
        if notes and notes.strip():
            parts.append(f"Notes: {notes.strip()}")
        return " | ".join(parts)
