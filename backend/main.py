import anyio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.schemas import QueryRequest, QueryResponse, HealthResponse
from backend.rag_service import rag_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to start non-blocking background model loader."""
    print("🚀 App startup: Triggering non-blocking background RAG loader...")
    rag_service.load_in_background()
    print("✅ FastAPI Server ready to accept connections instantaneously!")
    yield
    print("🛑 App shutdown: Cleaned up resources.")

app = FastAPI(
    title=settings.PROJECT_TITLE,
    version=settings.VERSION,
    description="FastAPI Backend for Egyptian Legal RAG Assistant",
    lifespan=lifespan
)

# CORS Middleware setup allowing Streamlit frontend and local origins
origins = [
    "http://localhost:8501",
    "http://127.0.0.1:8501",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["Root"])
async def root():
    """Root health check endpoint."""
    return {
        "message": "مرحباً بك في المساعد القانوني المصري API",
        "status": "online",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health", response_model=HealthResponse, tags=["Health"])
@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Returns vector store status, chunk count, and loaded models instantaneously."""
    return await anyio.to_thread.run_sync(rag_service.health_status)

@app.post("/query", response_model=QueryResponse, tags=["RAG Query"])
async def query_legal_rag(request: QueryRequest):
    """Receives an Egyptian legal query and returns answer with cited source articles."""
    if not request.question or not request.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="السؤال لا يمكن أن يكون فارغاً."
        )
    
    try:
        response = await anyio.to_thread.run_sync(
            rag_service.query,
            request.question.strip(),
            request.top_k or settings.DEFAULT_TOP_K,
            request.model_name
        )
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"حدث خطأ أثناء معالجة الاستعلام: {str(e)}"
        )

@app.post("/reindex", tags=["Admin"])
async def reindex_documents():
    """Triggers re-parsing of raw PDF documents and updates vector database."""
    try:
        await anyio.to_thread.run_sync(rag_service.ingest_documents, True)
        count = rag_service.collection.count() if rag_service.collection else 0
        return {"status": "success", "message": f"تمت إعادة فهرسة المستندات بنجاح. إجمالي القطع: {count}"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"حدث خطأ أثناء إعادة الفهرسة: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
