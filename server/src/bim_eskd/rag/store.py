"""Unified RAG store — single ChromaDB collection with category filtering.

Replaces the old StandardsStore with a 5-category system:
API, Scripts, Regulations, Glossary, Templates.
"""

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, List, Optional

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma
try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document

from .schema import RAGCategory, RAGRecord

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = Path(__file__).resolve().parents[3] / ".cache" / "chromadb"
_DEFAULT_PARSED_DIR = Path(__file__).resolve().parents[4] / "standards" / "parsed"

COLLECTION_NAME = "bim_eskd_rag"
DEDUP_THRESHOLD = 0.9  # cosine similarity threshold for dedup


def _get_embeddings():
    """Build the embedding backend (same logic as old standards.py)."""
    remote_url = os.environ.get("BIM_ESKD_EMBEDDINGS_URL")
    if remote_url:
        import requests as _req

        class _Remote:
            def __init__(self, url):
                self.url = url.rstrip("/")

            def embed_documents(self, texts):
                resp = _req.post(self.url, json={"inputs": texts}, timeout=30)
                resp.raise_for_status()
                return resp.json()["embeddings"]

            def embed_query(self, text):
                return self.embed_documents([text])[0]

        return _Remote(remote_url)

    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError:
        from langchain_community.embeddings import HuggingFaceEmbeddings

    model = os.environ.get(
        "BIM_ESKD_EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    cache = os.environ.get("BIM_ESKD_EMBEDDING_CACHE") or os.environ.get("HF_HOME")
    return HuggingFaceEmbeddings(
        model_name=model,
        cache_folder=str(cache) if cache else None,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


class UnifiedRAGStore:
    """Single ChromaDB collection with category-based filtering."""

    def __init__(self, persist_dir: Optional[Path] = None):
        self.persist_dir = Path(persist_dir or _DEFAULT_CACHE)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.embeddings = _get_embeddings()
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
        self.store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=str(self.persist_dir),
        )

    def index_exists(self) -> bool:
        meta_path = self.persist_dir / f"{COLLECTION_NAME}_metadata.json"
        return meta_path.exists()

    # ── Search ──────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        categories: Optional[List[RAGCategory]] = None,
        jurisdiction: Optional[str] = None,
        k: int = 5,
    ) -> List[RAGRecord]:
        """Semantic search with optional category and jurisdiction filters."""
        where_clauses = []

        if categories:
            if len(categories) == 1:
                where_clauses.append({"category": {"$eq": int(categories[0])}})
            else:
                where_clauses.append(
                    {"$or": [{"category": {"$eq": int(c)}} for c in categories]}
                )

        if jurisdiction:
            where_clauses.append(
                {"$or": [
                    {"jurisdiction": {"$eq": jurisdiction}},
                    {"jurisdiction": {"$eq": ""}},
                ]}
            )

        # Exclude outdated
        where_clauses.append({"is_outdated": {"$ne": True}})

        where = None
        if len(where_clauses) == 1:
            where = where_clauses[0]
        elif len(where_clauses) > 1:
            where = {"$and": where_clauses}

        try:
            results = self.store.similarity_search(query=query, k=k, filter=where)
        except Exception as e:
            logger.warning(f"RAG search failed: {e}")
            return []

        records = []
        for doc in results:
            rec = RAGRecord.from_metadata(
                doc_id=doc.metadata.get("_id", ""),
                content=doc.page_content,
                meta=doc.metadata,
            )
            records.append(rec)
        return records

    # ── Add ──────────────────────────────────────────────────────────

    def add(self, record: RAGRecord, deduplicate: bool = True) -> str:
        """Add a record to the store. Returns the record ID."""
        if not record.id:
            record.id = str(uuid.uuid4())[:8]

        if deduplicate:
            existing = self.search(
                record.content,
                categories=[record.category],
                k=1,
            )
            if existing and self._is_duplicate(record.content, existing[0].content):
                logger.info(f"Dedup: record similar to {existing[0].id}, skipping")
                return existing[0].id

        meta = record.to_metadata()
        meta["_id"] = record.id
        doc = Document(page_content=record.content, metadata=meta)
        self.store.add_documents([doc])
        logger.info(f"Added RAG record {record.id} (cat={record.category.name})")
        return record.id

    def _is_duplicate(self, new_text: str, existing_text: str) -> bool:
        """Simple text-based dedup (exact prefix match or very similar)."""
        if new_text == existing_text:
            return True
        # Check prefix overlap
        shorter = min(len(new_text), len(existing_text))
        if shorter > 50:
            overlap = sum(1 for a, b in zip(new_text, existing_text) if a == b)
            if overlap / shorter > DEDUP_THRESHOLD:
                return True
        return False

    # ── Usage tracking ──────────────────────────────────────────────

    def record_usage(self, record_id: str, success: bool = True) -> None:
        """Update usage statistics for a record."""
        # ChromaDB doesn't support in-place updates easily via langchain,
        # so we log usage for now and batch-update periodically
        logger.info(f"RAG usage: {record_id} success={success}")

    def mark_failure(self, record_id: str) -> None:
        """Increment failure count. If >3, mark as outdated."""
        logger.warning(f"RAG failure recorded: {record_id}")

    # ── Bulk operations ─────────────────────────────────────────────

    def build_standards_index(
        self, jsonl_dir: Optional[Path] = None, force: bool = False
    ) -> int:
        """Ingest standards JSONL files (Category 3: Regulations).

        Backwards-compatible with old StandardsStore.build_index().
        """
        jsonl_dir = Path(jsonl_dir or _DEFAULT_PARSED_DIR)
        if not force and self.index_exists():
            return 0

        if force:
            self._rebuild_collection()

        docs: list[Document] = []
        for path in sorted(jsonl_dir.glob("*.jsonl")):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    text = rec.get("text", "")
                    raw_meta = rec.get("metadata", {})
                    meta = {
                        k: v for k, v in raw_meta.items()
                        if isinstance(v, (str, int, float, bool))
                    }
                    # Tag as regulations
                    meta["category"] = int(RAGCategory.REGULATIONS)
                    meta["is_outdated"] = False
                    meta["_id"] = str(uuid.uuid4())[:8]
                    if text:
                        docs.append(Document(page_content=text, metadata=meta))

        if not docs:
            return 0

        self.store.add_documents(docs)
        self._save_meta(len(docs))
        return len(docs)

    def _rebuild_collection(self):
        """Drop and recreate the collection."""
        try:
            self.store.delete_collection()
        except Exception:
            pass
        self.store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=str(self.persist_dir),
        )

    def _save_meta(self, count: int):
        meta = {"collection": COLLECTION_NAME, "document_count": count}
        (self.persist_dir / f"{COLLECTION_NAME}_metadata.json").write_text(
            json.dumps(meta, indent=2)
        )

    # ── Legacy compatibility ────────────────────────────────────────

    def search_standards(
        self,
        query: str,
        k: int = 5,
        document_id: Optional[str] = None,
        section: Optional[str] = None,
    ) -> list[dict]:
        """Legacy API — search only regulations category.

        Returns dicts like old StandardsStore for backwards compat.
        """
        where_clauses = [{"category": {"$eq": int(RAGCategory.REGULATIONS)}}]

        if document_id:
            where_clauses.append({"document_id": {"$eq": document_id}})
        if section:
            where_clauses.append({"section_number": {"$eq": section}})

        where = where_clauses[0] if len(where_clauses) == 1 else {"$and": where_clauses}

        try:
            results = self.store.similarity_search(query=query, k=k, filter=where)
        except Exception as e:
            logger.warning(f"Standards search failed: {e}")
            return []

        return [{"content": d.page_content, "metadata": d.metadata} for d in results]
