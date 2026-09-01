# app/services/pdf_service.py

import fitz
import re
from rust_parser import extract_and_clean_pdf

async def extract_text_from_pdf(file_bytes: bytes) -> str:
    return extract_and_clean_pdf(file_bytes)

def chunk_text(text: str, chunk_size: int = 300, overlap: int = 20) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            space_index = text.rfind(' ', start, end)
            if space_index != -1:
                end = space_index
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        
    return chunks