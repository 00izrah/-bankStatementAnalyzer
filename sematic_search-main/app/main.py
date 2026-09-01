from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.services.ml_service import store
from app.api.v1.endpoints import router as api_router_v1
from app.api.v2.endpoints import router as api_router_v2
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError # Added for the retry logic
from app.models.database import Base, DATABASE_URL
import os
import time # Added for sleep

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("STARTING UPPP...")
    
    # 1. Attempt to connect to DB with retries
    from app.models.database import engine
    retries = 5
    connected = False
    
    while retries > 0:
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            Base.metadata.create_all(engine)
            print("✅ Database and pgvector initialized")
            connected = True
            break
        except OperationalError as e:
            retries -= 1
            print(f"⌛ Waiting for Postgres... ({retries} retries left)")
            time.sleep(2)
        except Exception as e:
            print(f"❌ Unexpected DB Error: {e}")
            break

    if not connected:
        print("🛑 Critical: Could not connect to Database. Search will be unavailable.")

    # 2. Existing FAISS load logic
    store.load()
    
    yield
    
    # On Shutdown
    store.save()

app = FastAPI(
    lifespan=lifespan,
    title="PDF Semantic Search API",
    description="API for semantic search in PDF documents",
    version="1.0.0"
)

app.include_router(api_router_v1, prefix="/api/v1")
app.include_router(api_router_v2, prefix="/api/v2")

@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Welcome, Peter. The Semantic Search API is running."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)