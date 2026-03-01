"""Standards RAG for the standalone server.

Thin wrapper around the same StandardsKnowledgeStore from bonsai-mcp,
but self-contained (no import from bonsai-mcp at runtime).
Uses the same ChromaDB collection ("standards") and JSONL ingestion.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma
try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document

logger = logging.getLogger(__name__)

# Default paths
_DEFAULT_CACHE = Path(__file__).resolve().parents[3] / ".cache" / "chromadb"
_DEFAULT_PARSED_DIR = Path(__file__).resolve().parents[4] / "standards" / "parsed"


def _get_embeddings():
    """Build the embedding backend."""
    remote_url = os.environ.get("BIM_ESKD_EMBEDDINGS_URL")
    if remote_url:
        # Inline minimal remote adapter
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

    model = os.environ.get("BIM_ESKD_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    cache = os.environ.get("BIM_ESKD_EMBEDDING_CACHE") or os.environ.get("HF_HOME")
    return HuggingFaceEmbeddings(
        model_name=model,
        cache_folder=str(cache) if cache else None,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


class StandardsStore:
    """ChromaDB-backed store for standards knowledge."""

    COLLECTION = "standards"

    def __init__(self, persist_dir: Optional[Path] = None):
        self.persist_dir = Path(persist_dir or _DEFAULT_CACHE)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.embeddings = _get_embeddings()
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
        self.store = Chroma(
            collection_name=self.COLLECTION,
            embedding_function=self.embeddings,
            persist_directory=str(self.persist_dir),
        )

    def index_exists(self) -> bool:
        return (self.persist_dir / f"{self.COLLECTION}_metadata.json").exists()

    def build_index(self, jsonl_dir: Optional[Path] = None, force: bool = False) -> int:
        """Ingest JSONL files from a directory."""
        jsonl_dir = Path(jsonl_dir or _DEFAULT_PARSED_DIR)
        if not force and self.index_exists():
            return 0

        if force and self.index_exists():
            self.store.delete_collection()
            self.store = Chroma(
                collection_name=self.COLLECTION,
                embedding_function=self.embeddings,
                persist_directory=str(self.persist_dir),
            )

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
                    meta = {k: v for k, v in rec.get("metadata", {}).items() if isinstance(v, (str, int, float, bool))}
                    if text:
                        docs.append(Document(page_content=text, metadata=meta))

        if not docs:
            return 0
        self.store.add_documents(docs)
        self._save_meta(len(docs))
        return len(docs)

    def search(
        self,
        query: str,
        k: int = 5,
        document_id: Optional[str] = None,
        section: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.index_exists():
            return []
        where = None
        parts = []
        if document_id:
            parts.append({"document_id": {"$eq": document_id}})
        if section:
            parts.append({"section_number": {"$eq": section}})
        if len(parts) == 1:
            where = parts[0]
        elif len(parts) > 1:
            where = {"$and": parts}

        results = self.store.similarity_search(query=query, k=k, filter=where)
        return [{"content": d.page_content, "metadata": d.metadata} for d in results]

    def _save_meta(self, count: int):
        meta = {"collection": self.COLLECTION, "document_count": count}
        (self.persist_dir / f"{self.COLLECTION}_metadata.json").write_text(
            json.dumps(meta, indent=2)
        )
