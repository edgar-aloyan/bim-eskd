"""RAG record schema and category definitions.

Five categories:
1. API      — ifcopenshell API docs and usage patterns
2. SCRIPTS  — Working code snippets (auto-saved from execute_code)
3. REGULATIONS — Standards (ГОСТ, ПУЭ, СП, IEC, NEC)
4. GLOSSARY — Terms in en/ru/hy with IFC mapping
5. TEMPLATES — ЕСКД constants, frame params, rendering presets
"""

from dataclasses import dataclass, field, asdict
from enum import IntEnum
from typing import Any, Optional


class RAGCategory(IntEnum):
    API = 1
    SCRIPTS = 2
    REGULATIONS = 3
    GLOSSARY = 4
    TEMPLATES = 5


# Display names for categories
CATEGORY_NAMES = {
    RAGCategory.API: "API Documentation",
    RAGCategory.SCRIPTS: "Code Scripts",
    RAGCategory.REGULATIONS: "Regulations & Standards",
    RAGCategory.GLOSSARY: "Glossary",
    RAGCategory.TEMPLATES: "Templates & Presets",
}


@dataclass
class RAGRecord:
    """A single RAG knowledge record."""
    id: str = ""
    category: RAGCategory = RAGCategory.API
    content: str = ""
    description: str = ""

    # Metadata
    source: str = ""           # e.g. "ifc_engine/wall.py", "ГОСТ 2.104-2006"
    jurisdiction: str = ""     # "RU", "AM", "US", "" (universal)
    locale: str = ""           # "ru", "en", "hy"
    tags: list[str] = field(default_factory=list)
    equivalent_rules: str = "" # cross-jurisdiction refs, e.g. "RU:ПУЭ 1.7|US:NEC 250"

    # Versioning
    version: int = 1
    is_outdated: bool = False

    # Usage tracking
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    def to_metadata(self) -> dict[str, Any]:
        """Flatten to ChromaDB-compatible metadata (str/int/float/bool only)."""
        return {
            "category": int(self.category),
            "description": self.description,
            "source": self.source,
            "jurisdiction": self.jurisdiction,
            "locale": self.locale,
            "tags": ",".join(self.tags),
            "equivalent_rules": self.equivalent_rules,
            "version": self.version,
            "is_outdated": self.is_outdated,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
        }

    @classmethod
    def from_metadata(cls, doc_id: str, content: str, meta: dict) -> "RAGRecord":
        """Reconstruct from ChromaDB document + metadata."""
        tags_raw = meta.get("tags", "")
        tags = [t for t in tags_raw.split(",") if t] if tags_raw else []
        return cls(
            id=doc_id,
            category=RAGCategory(meta.get("category", 1)),
            content=content,
            description=meta.get("description", ""),
            source=meta.get("source", ""),
            jurisdiction=meta.get("jurisdiction", ""),
            locale=meta.get("locale", ""),
            tags=tags,
            equivalent_rules=meta.get("equivalent_rules", ""),
            version=meta.get("version", 1),
            is_outdated=meta.get("is_outdated", False),
            usage_count=meta.get("usage_count", 0),
            success_count=meta.get("success_count", 0),
            failure_count=meta.get("failure_count", 0),
        )
