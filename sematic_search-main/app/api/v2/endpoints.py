from fastapi import APIRouter, UploadFile, File
from app.services.pdf_service import extract_text_from_pdf, chunk_text
from app.services.ml_service import generate_embeddings, store
from typing import List, Annotated
from pydantic import BaseModel
from app.services.llm_service import generate_answer
from app.models.database import SessionLocal
from app.models.database import ChatMessage
import hashlib

router = APIRouter()

def get_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()

@router.post("/upload")
async def upload_documents(files: Annotated[List[UploadFile], File(description="Multiple PDF files")]):
    total_chunks_added = 0
    processed_files = []
    skipped_files = []

    for file in files:
        content = await file.read()
        file_hash = get_file_hash(content)

        # Checking against the store's set of hashes
        if file_hash in store.seen_hashes:
            skipped_files.append(file.filename)
            continue
        
        # Process the new file
        text = await extract_text_from_pdf(content)
        chunks = chunk_text(text)
        embeddings = generate_embeddings(chunks)
    
        # Save to PostgreSQL via ml_service
        store.add_texts(chunks, embeddings, filename=file.filename)

        # Track hash to prevent duplicates in current session
        store.seen_hashes.add(file_hash)

        total_chunks_added += len(chunks)
        processed_files.append(file.filename)

    return {
        "filenames": processed_files,
        "skipped_files": skipped_files,
        "total_chunks": total_chunks_added,
        "message": f"Processed {len(processed_files)} new files. Skipped {len(skipped_files)} duplicates."
    }

class SearchRequest(BaseModel):
    query: str
    top_k: int = 3

@router.post("/search")
async def search_documents(request: SearchRequest, session_id: str = "default_user"):

    db = SessionLocal()

    try:

        history = db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at.desc()).limit(request.top_k)

        formatted_history = [{ "role": m.role, "content": m.content } for m in reversed(history)]

        user_msg = ChatMessage(session_id=session_id, role='user', content=request.query)
        db.add(user_msg)
        db.commit()

        query_vector = generate_embeddings([request.query])
        results = store.search(query_vector, k=request.top_k)

        ai_answer = await generate_answer(
            query=request.query,
            search_results=results,
            chat_history=formatted_history
        )

        ai_msg = ChatMessage(session_id=session_id, role="assistant", content=ai_answer)
        db.add(ai_msg)
        db.commit()

        return {
            "query": request.query,
            "ai_answer": ai_answer,
            "results": results
        }

    except Exception as e:
        db.rollback()
        return {
            "error": str(e)
        }
    finally:
        db.close()

