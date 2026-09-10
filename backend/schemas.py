from typing import List, Optional
from pydantic import BaseModel, Field

class QueryRequest(BaseModel):
    question: str = Field(..., description="السؤال القانوني باللغة العربية", example="ما هي عقوبة السير عكس الاتجاه؟")
    top_k: Optional[int] = Field(default=5, ge=1, le=20, description="عدد المواد القانونية المراد استرجاعها")
    model_name: Optional[str] = Field(default=None, description="اسم نموذج Ollama المطلوب استخدامه (مثل qwen2.5:7b أو qwen2.5:3b)")

class SourceChunk(BaseModel):
    law_title: str = Field(..., description="اسم المستند القانوني (الدستور، المرور، العمل...)")
    article_number: str = Field(..., description="رقم المادة القانونية")
    content: str = Field(..., description="النص الحرفي للمادة المسترجعة")
    score: float = Field(..., description="درجة التشابه / الصلة")

class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: List[SourceChunk]
    article_numbers: List[str]
    processing_time_sec: float

class HealthResponse(BaseModel):
    status: str
    vector_store_loaded: bool
    total_chunks: int
    embedding_model: str
    llm_model: str
