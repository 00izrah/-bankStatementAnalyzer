"""
Vector Store Service for Bank Statement Analyzer.

Provides user-scoped FAISS-backed vector indexes for semantic search over
transaction embeddings. Each user gets their own index file persisted to disk.
"""
import os
import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional

from django.conf import settings

from .embedding_service import EmbeddingService

logger = logging.getLogger('bankstatements')


class VectorStoreService:
    """
    User-scoped FAISS vector store for transaction embeddings.

    Each user's index is stored at:
        media/vector_indexes/user_{user_id}/index.faiss
        media/vector_indexes/user_{user_id}/metadata.json

    The metadata JSON maps FAISS internal IDs to transaction database PKs
    and their text representations for citation in LLM responses.

    Usage:
        store = VectorStoreService(user)
        store.index_transactions(queryset)
        results = store.search("grocery shopping", top_k=5)
    """

    def __init__(self, user):
        self.user = user
        self.embedding_service = EmbeddingService()
        self.dimension = settings.EMBEDDING_DIMENSION

        # Per-user directory
        self.index_dir = os.path.join(
            settings.FAISS_INDEX_DIR, f"user_{user.id}"
        )
        os.makedirs(self.index_dir, exist_ok=True)

        self.index_path = os.path.join(self.index_dir, "index.faiss")
        self.meta_path = os.path.join(self.index_dir, "metadata.json")

        # Lazily loaded
        self._index = None
        self._metadata = None

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _get_faiss(self):
        """Import FAISS lazily to avoid startup cost if not used."""
        try:
            import faiss
            return faiss
        except ImportError:
            raise ImportError(
                "faiss-cpu is not installed. Run: pip install faiss-cpu"
            )

    def _load_index(self):
        """Load index and metadata from disk, or create empty ones."""
        faiss = self._get_faiss()

        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
            self._index = faiss.read_index(self.index_path)
            with open(self.meta_path, "r", encoding="utf-8") as f:
                self._metadata = json.load(f)
            logger.info(
                f"Loaded FAISS index for user {self.user.id} "
                f"({self._index.ntotal} vectors)"
            )
        else:
            # Create a new flat L2 index (exact search, fast for <100k vectors)
            self._index = faiss.IndexFlatIP(self.dimension)  # Inner Product (cosine on normalized vecs)
            self._metadata = []
            logger.info(f"Created new FAISS index for user {self.user.id}")

    def _save_index(self):
        """Persist index and metadata to disk."""
        if self._index is None:
            return
        faiss = self._get_faiss()
        faiss.write_index(self._index, self.index_path)
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(self._metadata, f, ensure_ascii=False)
        logger.info(
            f"Saved FAISS index for user {self.user.id} "
            f"({self._index.ntotal} vectors)"
        )

    @property
    def index(self):
        if self._index is None:
            self._load_index()
        return self._index

    @property
    def metadata(self):
        if self._metadata is None:
            self._load_index()
        return self._metadata

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_transactions(self, transactions_queryset) -> int:
        """
        Build or rebuild vector embeddings for the given transactions.

        Args:
            transactions_queryset: Django QuerySet of Transaction objects.

        Returns:
            Number of transactions indexed.
        """
        transactions = list(
            transactions_queryset.select_related('category', 'uploaded_file')
        )

        if not transactions:
            return 0

        # Build text representations
        texts = []
        meta_entries = []
        for txn in transactions:
            text = EmbeddingService.build_transaction_text(
                date=str(txn.date),
                description=txn.description,
                amount=txn.amount,
                category_name=txn.category.name if txn.category else None,
                notes=txn.notes,
            )
            texts.append(text)
            meta_entries.append({
                "transaction_id": txn.id,
                "uploaded_file_id": txn.uploaded_file_id,
                "date": str(txn.date),
                "description": txn.description[:200],
                "amount": str(txn.amount),
                "category": txn.category.name if txn.category else "Uncategorized",
                "text": text,
            })

        # Generate embeddings
        embeddings = self.embedding_service.embed_texts(texts)

        # Reset and rebuild index (full rebuild strategy — simple & correct)
        faiss = self._get_faiss()
        self._index = faiss.IndexFlatIP(self.dimension)
        self._index.add(embeddings)
        self._metadata = meta_entries

        self._save_index()
        logger.info(
            f"Indexed {len(transactions)} transactions for user {self.user.id}"
        )
        return len(transactions)

    def add_transactions(self, transactions_queryset) -> int:
        """
        Incrementally add new transactions to the existing index.

        Args:
            transactions_queryset: Django QuerySet of new Transaction objects.

        Returns:
            Number of transactions added.
        """
        transactions = list(
            transactions_queryset.select_related('category', 'uploaded_file')
        )

        if not transactions:
            return 0

        # Build text representations
        texts = []
        meta_entries = []
        existing_ids = {m["transaction_id"] for m in self.metadata}

        for txn in transactions:
            if txn.id in existing_ids:
                continue  # Already indexed

            text = EmbeddingService.build_transaction_text(
                date=str(txn.date),
                description=txn.description,
                amount=txn.amount,
                category_name=txn.category.name if txn.category else None,
                notes=txn.notes,
            )
            texts.append(text)
            meta_entries.append({
                "transaction_id": txn.id,
                "uploaded_file_id": txn.uploaded_file_id,
                "date": str(txn.date),
                "description": txn.description[:200],
                "amount": str(txn.amount),
                "category": txn.category.name if txn.category else "Uncategorized",
                "text": text,
            })

        if not texts:
            return 0

        # Generate embeddings and add to index
        embeddings = self.embedding_service.embed_texts(texts)
        self.index.add(embeddings)
        self.metadata.extend(meta_entries)

        self._save_index()
        logger.info(
            f"Added {len(texts)} transactions to index for user {self.user.id}"
        )
        return len(texts)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 5,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search over the user's transaction index.

        Args:
            query: Natural language search query.
            top_k: Number of results to return.
            date_from: Optional date filter (inclusive, YYYY-MM-DD).
            date_to: Optional date filter (inclusive, YYYY-MM-DD).

        Returns:
            List of dicts with keys: transaction_id, date, description,
            amount, category, text, score.
        """
        if self.index.ntotal == 0:
            return []

        # Encode query
        query_vector = self.embedding_service.embed_query(query)

        # Search — retrieve more than top_k if we're filtering by date
        search_k = min(top_k * 3, self.index.ntotal) if (date_from or date_to) else min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query_vector, search_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue

            meta = self.metadata[idx]

            # Apply optional date filters
            if date_from and meta["date"] < date_from:
                continue
            if date_to and meta["date"] > date_to:
                continue

            results.append({
                **meta,
                "score": float(score),
            })

            if len(results) >= top_k:
                break

        return results

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear_index(self):
        """Delete the user's entire vector index."""
        faiss = self._get_faiss()
        self._index = faiss.IndexFlatIP(self.dimension)
        self._metadata = []
        self._save_index()
        logger.info(f"Cleared FAISS index for user {self.user.id}")

    def get_index_stats(self) -> Dict[str, Any]:
        """Return statistics about the user's index."""
        return {
            "total_vectors": self.index.ntotal,
            "dimension": self.dimension,
            "index_path": self.index_path,
            "index_exists": os.path.exists(self.index_path),
        }
