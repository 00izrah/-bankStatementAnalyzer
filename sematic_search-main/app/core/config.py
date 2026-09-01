# app/core/config.py

class Settings:
    PROJECT_NAME: str = "PDF Semantic Search"
    MODEL_NAME: str = "all-MiniLM-L6-v2"
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50

settings = Settings()