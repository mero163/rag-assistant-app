import time
import os
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from sentence_transformers import SentenceTransformer
import ollama

from backend.config import settings
from backend.text_processor import extract_pdf_text, parse_law_articles, extract_article_number
from backend.schemas import SourceChunk, QueryResponse, HealthResponse

logger = logging.getLogger("rag_service")
logging.basicConfig(level=logging.INFO)

class RAGService:
    def __init__(self):
        self.embedding_model: Optional[SentenceTransformer] = None
        self.chroma_client: Optional[chromadb.PersistentClient] = None
        self.collection: Optional[chromadb.Collection] = None
        self.is_loaded: bool = False
        self.is_loading: bool = False
        self._lock = threading.Lock()

    def load_in_background(self):
        """Starts background loading of models and vector DB if not already loaded."""
        if self.is_loaded or self.is_loading:
            return
        
        thread = threading.Thread(target=self.load, kwargs={"force_reindex": False}, daemon=True)
        thread.start()

    def load(self, force_reindex: bool = False):
        """Initializes embedding model and vector database safely."""
        with self._lock:
            if self.is_loaded and not force_reindex:
                return
            
            self.is_loading = True
            try:
                if self.embedding_model is None:
                    logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL_NAME}...")
                    self.embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
                
                if self.chroma_client is None or force_reindex:
                    logger.info(f"Initializing ChromaDB persistent storage at {settings.VECTOR_STORE_DIR}...")
                    settings.VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
                    self.chroma_client = chromadb.PersistentClient(path=str(settings.VECTOR_STORE_DIR))

                # Get or create collection with cosine similarity
                self.collection = self.chroma_client.get_or_create_collection(
                    name=settings.CHROMA_COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"}
                )
                
                # Auto-ingest documents if collection is empty or reindex requested
                if self.collection.count() == 0 or force_reindex:
                    logger.info("Vector collection is empty or reindex requested. Ingesting raw documents...")
                    self.ingest_documents(force_reindex=force_reindex)
                else:
                    logger.info(f"Loaded existing vector collection with {self.collection.count()} article chunks.")
                    
                self.is_loaded = True
            except Exception as e:
                logger.error(f"Error loading RAG service: {e}")
            finally:
                self.is_loading = False

    def ingest_documents(self, force_reindex: bool = False):
        """
        Scans raw_documents folder, cleans PDFs, chunks by article,
        computes embeddings first, and then performs an atomic swap into ChromaDB.
        """
        pdf_files = list(settings.RAW_DOCS_DIR.glob("*.pdf"))
        if not pdf_files:
            logger.warning(f"No PDF files found in {settings.RAW_DOCS_DIR}")
            return

        all_chunks: List[Dict[str, Any]] = []
        for pdf_file in pdf_files:
            law_title = pdf_file.stem.replace("-", " ")
            logger.info(f"Processing PDF document: {pdf_file.name}...")
            raw_text = extract_pdf_text(pdf_file)
            doc_chunks = parse_law_articles(raw_text, law_title)
            all_chunks.extend(doc_chunks)

        if not all_chunks:
            logger.warning("No article chunks parsed from documents.")
            return

        texts = [c["content"] for c in all_chunks]
        metadatas = [
            {
                "law_title": c["law_title"],
                "article_number": c["article_number"]
            }
            for c in all_chunks
        ]
        ids = [c["chunk_id"] for c in all_chunks]

        logger.info(f"Generating embeddings for {len(texts)} chunks with {settings.EMBEDDING_MODEL_NAME}...")
        embeddings = self.embedding_model.encode(texts, show_progress_bar=False, batch_size=32)

        # Atomic Collection Swap
        if force_reindex or (self.collection and self.collection.count() > 0):
            try:
                self.chroma_client.delete_collection(settings.CHROMA_COLLECTION_NAME)
            except Exception:
                pass
            
            self.collection = self.chroma_client.create_collection(
                name=settings.CHROMA_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )

        # Batch insert into ChromaDB
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            end_idx = i + batch_size
            self.collection.add(
                embeddings=embeddings[i:end_idx].tolist(),
                documents=texts[i:end_idx],
                metadatas=metadatas[i:end_idx],
                ids=ids[i:end_idx]
            )

        logger.info(f"Successfully indexed {self.collection.count()} chunks into ChromaDB.")

    def get_available_llm(self, requested_model: Optional[str] = None) -> str:
        """Dynamically validates Ollama models and falls back to installed models."""
        available_names = []
        try:
            resp = ollama.list()
            models_list = getattr(resp, 'models', []) if hasattr(resp, 'models') else (resp.get('models', []) if isinstance(resp, dict) else [])
            for m in models_list:
                if hasattr(m, 'model'):
                    available_names.append(m.model)
                elif isinstance(m, dict) and 'name' in m:
                    available_names.append(m['name'])
        except Exception as e:
            logger.warning(f"Failed to check Ollama models (will use fallback): {e}")
            # Return fallback immediately without blocking
            return settings.FALLBACK_LLM_MODEL

        # If a requested model is passed, check if it exists in Ollama
        if requested_model and available_names:
            for name in available_names:
                if requested_model == name or requested_model in name or name in requested_model:
                    return name

        # Preference hierarchy among installed models
        if available_names:
            for candidate in [settings.DEFAULT_LLM_MODEL, settings.FALLBACK_LLM_MODEL, "mistral:latest", "mistral"]:
                for name in available_names:
                    if candidate in name:
                        return name
            return available_names[0]

        return settings.FALLBACK_LLM_MODEL

    def query(self, question: str, top_k: int = 5, model_name: Optional[str] = None) -> QueryResponse:
        """Retrieves context chunks and generates a grounded Egyptian legal answer."""
        start_time = time.time()
        
        if not self.is_loaded:
            self.load()

        # Step 1: Embed question and query ChromaDB
        query_vector = self.embedding_model.encode([question])[0].tolist()
        
        try:
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            if "dimension" in str(e).lower() or (self.collection and self.collection.count() == 0):
                logger.warning("Empty or mismatched collection detected in ChromaDB. Auto-reindexing...")
                self.ingest_documents(force_reindex=True)
                results = self.collection.query(
                    query_embeddings=[query_vector],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances"]
                )
            else:
                raise e

        docs = results["documents"][0] if results["documents"] else []
        metas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []

        # Auto-heal if collection returned 0 docs
        if not docs and self.collection.count() == 0:
            logger.warning("Collection was empty during query. Ingesting documents now...")
            self.ingest_documents(force_reindex=True)
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                include=["documents", "metadatas", "distances"]
            )
            docs = results["documents"][0] if results["documents"] else []
            metas = results["metadatas"][0] if results["metadatas"] else []
            distances = results["distances"][0] if results["distances"] else []

        sources: List[SourceChunk] = []
        article_numbers: List[str] = []
        formatted_context_blocks: List[str] = []

        for idx, doc in enumerate(docs):
            law_title = metas[idx].get("law_title", "غير محدد")
            art_num = metas[idx].get("article_number", extract_article_number(doc))
            dist = float(distances[idx]) if idx < len(distances) else 0.0
            
            # Cosine similarity score conversion (1 - distance)
            similarity_score = max(0.0, round(1.0 - dist, 4))

            sources.append(
                SourceChunk(
                    law_title=law_title,
                    article_number=art_num,
                    content=doc,
                    score=similarity_score
                )
            )

            if art_num != "عام" and art_num not in article_numbers:
                article_numbers.append(art_num)

            formatted_context_blocks.append(
                f"--- [النص المرجعي {idx+1}] ---\n"
                f"التشريع: {law_title}\n"
                f"المادة: {art_num}\n"
                f"محتوى النص:\n{doc}\n"
            )

        context_text = "\n".join(formatted_context_blocks)

        # Step 2: System Prompt for LLM
        prompt = f"""أنت مساعد قانوني مصري خبير ومباشر ودقيق جداً.
مهمتك: اقرأ النصوص المرجعية المرفقة من التشريعات المصرية وأجب عن السؤال الموجه بدقة متناهية.

قواعد صارمة للإجابة:
1. استند فقط وحصرياً إلى المعلومات الواردة في النصوص المرجعية المرفقة.
2. اذكر رقم المادة واسم القانون بالحرف كما هو مكتوب في النصوص المرفقة (مثال: طبقاً للمادة 2 من قانون المرور...).
3. لا تقم بتخمين أو إضافة أي معلومات قانونية من خارج النصوص المرجعية.
4. إذا لم تجد الإجابة في النصوص المرفقة، اكتب فقط: "لا توجد معلومات كافية في المستندات المتاحة للإجابة على هذا السؤال."

### النصوص المرجعية:
{context_text}

### السؤال:
{question}

### الإجابة (مع ذكر أرقام المواد والنصوص القانونية بدقة):"""

        selected_model = self.get_available_llm(model_name)
        logger.info(f"Generating LLM response using verified Ollama model: {selected_model}...")

        try:
            response = ollama.chat(
                model=selected_model,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": 0.05,
                    "top_p": 0.85,
                    "repeat_penalty": 1.1
                }
            )
            answer_text = response["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Error during Ollama generation with {selected_model}: {e}")
            fallback_model = settings.FALLBACK_LLM_MODEL
            if selected_model != fallback_model:
                try:
                    logger.info(f"Retrying with fallback model: {fallback_model}...")
                    response = ollama.chat(
                        model=fallback_model,
                        messages=[{"role": "user", "content": prompt}],
                        options={"temperature": 0.05}
                    )
                    answer_text = response["message"]["content"].strip()
                except Exception as fb_e:
                    answer_text = f"عذراً، حدث خطأ أثناء الاتصال بنموذج الذكاء الاصطناعي: {str(fb_e)}"
            else:
                answer_text = f"عذراً، حدث خطأ أثناء الاتصال بنموذج الذكاء الاصطناعي: {str(e)}"

        elapsed_time = round(time.time() - start_time, 2)

        return QueryResponse(
            question=question,
            answer=answer_text,
            sources=sources,
            article_numbers=article_numbers,
            processing_time_sec=elapsed_time
        )

    def health_status(self) -> HealthResponse:
        """Returns health diagnostics of RAG service instantaneously."""
        try:
            count = 0
            if self.collection and self.is_loaded:
                try:
                    count = self.collection.count()
                except Exception as e:
                    logger.warning(f"Could not get collection count: {e}")
                    count = 0
        except Exception as e:
            logger.warning(f"Error accessing collection: {e}")
            count = 0
            
        if self.is_loaded:
            status_str = "healthy"
        elif self.is_loading:
            status_str = "initializing"
        else:
            status_str = "standby"

        return HealthResponse(
            status=status_str,
            vector_store_loaded=self.is_loaded,
            total_chunks=count,
            embedding_model=settings.EMBEDDING_MODEL_NAME,
            llm_model=self.get_available_llm()
        )

# Global singleton instance
rag_service = RAGService()
