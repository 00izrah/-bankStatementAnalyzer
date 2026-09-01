# 🔍 PDF Semantic Search

![PDF Semantic Search Hero](pdf_semantic_search_hero.png)

> **Elevate your document intelligence.** A state-of-the-art Retrieval-Augmented Generation (RAG) platform that transforms static PDFs into interactive, searchable knowledge bases using high-performance Rust parsing and hybrid vector storage.

---

## 🚀 Overview

**PDF Semantic Search** is a powerful, production-ready solution for intelligent document interaction. By combining the speed of **Rust** with the flexibility of **FastAPI** and the precision of **Llama 3.1**, this project enables users to upload vast amounts of PDF data and perform lightning-fast semantic queries that go beyond simple keyword matching.

### 🏆 Key Accomplishments

- **Hybrid Python-Rust Architecture**: Integrated a custom high-performance Rust parser (`lopdf`) via PyO3 to handle complex PDF text extraction with significantly lower latency than traditional Python libraries.
- **Advanced RAG Pipeline**: Built a robust Retrieval-Augmented Generation (RAG) workflow using Groq's high-speed inference (Llama 3.1) and Sentence Transformers.
- **Sub-linear Scaling**: Leverages `pgvector` and PostgreSQL for persistent, indexed vector storage, ensuring the system scales efficiently with your document library.
- **Intelligent Deduplication**: Implemented SHA-256 fingerprinting to prevent redundant processing and storage of duplicate documents.
- **Context-Aware Conversations**: Feature-complete chat history management, allowing the system to understand follow-up questions and maintain conversational context.

---

## ✨ Features

- 📁 **Multi-Document Upload**: Concurrent processing of multiple PDF files.
- 🦀 **Rust-Powered Extraction**: Clean, accurate text extraction using a custom Rust-based parser.
- 🧠 **Semantic Understanding**: Uses metadata-enriched embeddings for deeper search context.
- 💬 **Smart Citations**: AI-generated answers include direct references and source tracking.
- 🐳 **Dockerized Deployment**: Fully containerized environment for seamless setup and scaling.
- 🔄 **Efficient Deduplication**: Skips already-processed files automatically based on content hashes.

---

## 🛠️ Tech Stack

### Backend & AI

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12+)
- **LLM**: Llama 3.1 (via [Groq](https://groq.com/))
- **Embeddings**: `all-MiniLM-L6-v2` ([Sentence-Transformers](https://www.sbert.net/))
- **Performance**: [Rust](https://www.rust-lang.org/) (via [PyO3](https://pyo3.rs/))
- **Parser**: `lopdf` (Rust) & `PyMuPDF` (Python)
- **Search**: [FAISS](https://github.com/facebookresearch/faiss) & [pgvector](https://github.com/pgvector/pgvector)

### Infrastructure

- **Database**: PostgreSQL (Vector-enabled)
- **ORM**: SQLAlchemy
- **Containerization**: Docker & Docker Compose
- **Dependency Management**: [uv](https://github.com/astral-sh/uv)

---

## 🏗️ Architecture

```mermaid
graph TD
    User([User]) --> API[FastAPI Backend]
    API --> RustParser[Rust Parser Module]
    RustParser --> Text[Cleaned Text]
    Text --> Embedder[Sentence Transformer]
    Embedder --> PG[(Postgres + pgvector)]
    API --> LLM[Llama 3.1 via Groq]
    LLM --> Answer[Contextual Answer + Citations]
    PG -.-> LLM
```

---

## 🚦 Getting Started

### 1. Prerequisites

- [Docker](https://www.docker.com/) & [Docker Compose](https://docs.docker.com/compose/)
- [uv](https://github.com/astral-sh/uv) (optional, for local development)
- [Groq API Key](https://console.groq.com/keys)

### 2. Setup Environment

Create a `.env` file in the root directory:

```env
GROQ_API_KEY=your_groq_api_key_here
DATABASE_URL=postgresql://admin:password@localhost:5432/vector_db
```

### 3. Build and Run

```bash
# Start the vector database
docker-compose up -d

# Install dependencies and build Rust extension
uv sync
uv run maturin develop --manifest-path rust_parser/Cargo.toml

# Start the application
uv run uvicorn main:app --reload
```

---

## 📖 API Documentation

Once the server is running, explore the interactive documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Key Endpoints

- `POST /api/v2/upload`: Upload PDFs to the knowledge base.
- `POST /api/v2/search`: Perform semantic search and get AI-generated answers.

---

## 🗺️ Roadmap

- [ ] **Cross-file Summarization**: Generate insights across the entire document library.
- [ ] **Frontend Dashboard**: A sleek React/Next.js interface for document management.
- [ ] **OCR Support**: Integration with Tesseract for scanned/image-based PDFs.
- [ ] **Custom Embedding Models**: Support for larger or fine-tuned models.

---

<p align="center">
  Developed with ❤️ for high-performance semantic search.
</p>
