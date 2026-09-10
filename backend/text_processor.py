import re
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional
from pypdf import PdfReader

def normalize_arabic_text(text: str) -> str:
    """
    Cleans and normalizes Arabic text extracted from legal PDFs.
    1. Converts presentation forms / ligatures (NFKC) to standard Arabic Unicode.
    2. Strips Arabic diacritics (Tashkeel).
    3. Cleans non-printable control characters while preserving legal formatting.
    """
    if not text:
        return ""
    
    # NFKC Unicode normalization (converts ligatures like ﻣﺎﺩﺓ to مادة)
    text = unicodedata.normalize("NFKC", text)
    
    # Strip Tashkeel (diacritics)
    text = re.sub(r"[\u0617-\u061A\u064B-\u0652]", "", text)
    
    # Remove control characters but preserve newlines, tabs, spaces
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    
    # Replace multiple horizontal spaces with a single space
    text = re.sub(r"[ \t]+", " ", text)
    
    # Clean multiple consecutive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    return text.strip()

def extract_pdf_text(file_path: Path) -> str:
    """Reads all pages from a PDF file and returns normalized text."""
    reader = PdfReader(str(file_path))
    pages_text = []
    
    for i, page in enumerate(reader.pages):
        page_content = page.extract_text() or ""
        if page_content.strip():
            pages_text.append(page_content)
            
    full_raw_text = "\n".join(pages_text)
    return normalize_arabic_text(full_raw_text)

def extract_article_number(text: str) -> str:
    """Extracts standardized article number or header identifier from a text snippet."""
    patterns = [
        r"(?:المادة|مادة)\s*[\(\（]?\s*([0-9\u0660-\u0669]+|الأولى|الثانية|الثالثة|الرابعة|الخامسة|السادسة|السابعة|الثامنة|التاسعة|العاشرة|[أ-ي\s\/]+)\s*[\)\）]?",
        r"[\(\（]\s*(?:المادة|مادة)\s*([0-9\u0660-\u0669]+|الأولى|الثانية|الثالثة|الرابعة|الخامسة|السادسة|السابعة|الثامنة|التاسعة|العاشرة|[أ-ي\s\/]+)\s*[\)\）]"
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            num = match.group(1).strip()
            # Clean outer punctuation
            num = re.sub(r"^[\(\（\:\-\.\s]+|[\)\）\:\-\.\s]+$", "", num)
            return num
    return "عام"

def parse_law_articles(text: str, law_title: str) -> List[Dict[str, Any]]:
    """
    Article-based Chunking Strategy.
    Splits legal documents by Article boundaries (مادة X / المادة X).
    Preserves law title and article number in metadata for precise retrieval.
    """
    normalized = normalize_arabic_text(text)
    
    # Regex lookahead to find article start boundaries
    # Matches: مادة (1), المادة ( الأولى ), مادة 206, مادة (3/ فقرة ثانية), ( المادة الأولى )
    article_regex = re.compile(
        r"(?=(?:^|\n)\s*[\(\（\s]*(?:المادة|مادة)\s*[\(\（\s]*"
        r"(?:\d+|[\u0660-\u0669]+|الأولى|الثانية|الثالثة|الرابعة|الخامسة|السادسة|السابعة|الثامنة|التاسعة|العاشرة|[أ-ي\s\/]+)"
        r"\s*[\)\）\s]*[\)\）\s]*[\:\-\.]?)",
        re.MULTILINE | re.IGNORECASE
    )
    
    blocks = article_regex.split(normalized)
    chunks: List[Dict[str, Any]] = []
    
    chunk_counter = 0
    for block in blocks:
        block_clean = block.strip()
        if not block_clean or len(block_clean) < 15:
            continue
            
        art_num = extract_article_number(block_clean)
        words = block_clean.split()
        
        # Sub-chunk exceptionally long articles (> 800 words) while keeping article context
        if len(words) > 800:
            sub_size = 500
            overlap = 60
            for start_idx in range(0, len(words), sub_size - overlap):
                sub_words = words[start_idx : start_idx + sub_size]
                sub_text = " ".join(sub_words)
                chunk_counter += 1
                chunks.append({
                    "chunk_id": f"{law_title}_art_{art_num}_p{chunk_counter}",
                    "law_title": law_title,
                    "article_number": art_num,
                    "content": sub_text
                })
        else:
            chunk_counter += 1
            chunks.append({
                "chunk_id": f"{law_title}_art_{art_num}_{chunk_counter}",
                "law_title": law_title,
                "article_number": art_num,
                "content": block_clean
            })
            
    return chunks
