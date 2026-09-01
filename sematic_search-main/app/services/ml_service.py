from sentence_transformers import SentenceTransformer
import numpy as np
from app.models.database import SessionLocal, DocumentChunk
import json

class VectorStore:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.seen_hashes = set()

    def add_texts(self, texts: list[str], embeddings: np.ndarray, filename: str):
        
        db = SessionLocal()
        try:
            for text, emb in zip(texts, embeddings):
                chunk = DocumentChunk(
                    content=text,
                    filename=filename,
                    embedding=emb.tolist() 
                )
                db.add(chunk)
            db.commit()
            print(f"✅ DB: Persisted {len(texts)} chunks for {filename}")
        except Exception as e:
            db.rollback()
            print(f"❌ DB Error: {e}")
            raise e
        finally:
            db.close()

    def search(self, query_vector: np.ndarray, k: int = 3):
        db = SessionLocal()
        try:
            v = query_vector[0].tolist()

            results = db.query(DocumentChunk).order_by(
                DocumentChunk.embedding.l2_distance(v)
            ).limit(k).all()

            return [{"text": r.content, "source": r.filename} for r in results]
        finally:
            db.close()

    def save(self, folder=None): pass
    def load(self, folder=None): pass

store = VectorStore()

def generate_embeddings(chunks: list[str]):
    return store.model.encode(chunks)