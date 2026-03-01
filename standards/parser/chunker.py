"""Chunker for parsed standards documents.

Splits sections into embedding-sized chunks while preserving table integrity.
Output: JSONL format suitable for ChromaDB ingestion.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .pdf_parser import ParsedDocument, Section, Table

logger = logging.getLogger(__name__)

# Target chunk size (characters). Tables are never split.
DEFAULT_CHUNK_SIZE = 1500
DEFAULT_CHUNK_OVERLAP = 200


@dataclass
class Chunk:
    text: str
    metadata: dict

    def to_jsonl(self) -> str:
        return json.dumps(
            {"text": self.text, "metadata": self.metadata},
            ensure_ascii=False,
        )


class StandardsChunker:
    """Splits a ParsedDocument into embedding chunks."""

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_document(self, doc: ParsedDocument) -> list[Chunk]:
        """Convert a parsed document into chunks for embedding."""
        chunks: list[Chunk] = []
        for section in doc.sections:
            chunks.extend(self._chunk_section(doc, section))
        logger.info(
            f"Document '{doc.document_id}': {len(doc.sections)} sections -> {len(chunks)} chunks"
        )
        return chunks

    def _chunk_section(
        self, doc: ParsedDocument, section: Section
    ) -> list[Chunk]:
        """Chunk a single section, keeping tables intact."""
        base_meta = {
            "document_id": doc.document_id,
            "document_title": doc.title,
            "section_number": section.number,
            "section_title": section.title,
            "section_level": section.level,
            "page_start": section.page_start,
            "page_end": section.page_end,
            "type": "standard",
        }
        base_meta.update(doc.metadata)

        chunks: list[Chunk] = []

        # Chunk tables separately (never split a table)
        for i, table in enumerate(section.tables):
            table_md = table.to_markdown()
            if not table_md:
                continue
            header = self._section_header(doc, section)
            text = f"{header}\n\n{table_md}"
            meta = {
                **base_meta,
                "content_type": "table",
                "table_index": i,
                "table_caption": table.caption,
                "table_page": table.page,
            }
            chunks.append(Chunk(text=text, metadata=meta))

        # Chunk prose text
        text = section.text.strip()
        if not text:
            return chunks

        header = self._section_header(doc, section)
        paragraphs = self._split_paragraphs(text)

        current = header + "\n\n"
        chunk_idx = 0
        for para in paragraphs:
            if len(current) + len(para) > self.chunk_size and len(current) > len(header) + 10:
                meta = {
                    **base_meta,
                    "content_type": "text",
                    "chunk_index": chunk_idx,
                }
                chunks.append(Chunk(text=current.strip(), metadata=meta))
                chunk_idx += 1
                # Overlap: keep last portion of previous chunk
                overlap_text = current[-self.chunk_overlap:] if len(current) > self.chunk_overlap else ""
                current = header + "\n\n" + overlap_text + "\n"
            current += para + "\n"

        # Flush remaining
        if current.strip() and len(current) > len(header) + 10:
            meta = {
                **base_meta,
                "content_type": "text",
                "chunk_index": chunk_idx,
            }
            chunks.append(Chunk(text=current.strip(), metadata=meta))

        return chunks

    def _section_header(self, doc: ParsedDocument, section: Section) -> str:
        """Create a context header for the chunk."""
        parts = [doc.document_id]
        if section.number:
            parts.append(f"п. {section.number}")
        if section.title:
            parts.append(section.title)
        return " — ".join(parts)

    def _split_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs on double newlines or numbered items."""
        # Split on double newline
        raw = text.split("\n\n")
        paragraphs: list[str] = []
        for block in raw:
            block = block.strip()
            if block:
                paragraphs.append(block)
        return paragraphs


def process_pdf(
    pdf_path: str | Path,
    output_path: str | Path | None = None,
    document_id: str = "",
    title: str = "",
    metadata: dict | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[Chunk]:
    """Convenience: parse a PDF and produce chunks.

    If output_path is given, writes JSONL file.
    Returns the list of chunks.
    """
    from .pdf_parser import StandardsPDFParser

    parser = StandardsPDFParser(pdf_path)
    doc = parser.parse(document_id=document_id, title=title, metadata=metadata)
    chunker = StandardsChunker(chunk_size=chunk_size)
    chunks = chunker.chunk_document(doc)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(chunk.to_jsonl() + "\n")
        logger.info(f"Wrote {len(chunks)} chunks to {output_path}")

    return chunks
