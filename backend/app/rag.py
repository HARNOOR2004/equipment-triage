import re
from pathlib import Path
from rank_bm25 import BM25Okapi

KB_DIR = Path(__file__).resolve().parent.parent / "kb"
SECTION_RE = re.compile(r"^## \[([A-Z]+-\d+\.\d+)\] (.+)$", re.M)

class RetrievalError(Exception):
    pass

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())

def _load_chunks() -> list[dict]:
    files = list(KB_DIR.glob("*.md"))
    if not files:
        raise RetrievalError(f"No knowledge base files found in {KB_DIR}")
    chunks = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        matches = list(SECTION_RE.finditer(text))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunks.append({
                "id": m.group(1),
                "title": m.group(2),
                "equipment_type": f.stem,
                "text": text[m.end():end].strip(),
            })
    return chunks

_CHUNKS: list[dict] | None = None

def get_chunks() -> list[dict]:
    global _CHUNKS
    if _CHUNKS is None:
        _CHUNKS = _load_chunks()
    return _CHUNKS

def retrieve(equipment_type: str, query: str, k: int = 4) -> list[dict]:
    pool = [c for c in get_chunks() if c["equipment_type"] == equipment_type]
    if not pool:
        raise RetrievalError(f"No manual sections for equipment type '{equipment_type}'")
    bm25 = BM25Okapi([_tokenize(c["title"] + " " + c["text"]) for c in pool])
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(zip(pool, scores), key=lambda x: x[1], reverse=True)
    hits = [{**c, "score": float(s)} for c, s in ranked[:k] if s > 0]
    if not hits:
        raise RetrievalError("No relevant manual sections found for this report")
    return hits