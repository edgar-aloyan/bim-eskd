"""PDF parser for standards documents (ПУЭ, ГОСТ, СП, IEC).

Extracts text with structure (sections, tables, formulas) from PDF files.
Uses pymupdf for text extraction and pdfplumber for table detection.
"""

import re
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TableCell:
    text: str
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1


@dataclass
class Table:
    rows: list[list[str]]
    page: int
    caption: str = ""

    def to_markdown(self) -> str:
        if not self.rows:
            return ""
        lines = []
        if self.caption:
            lines.append(f"**{self.caption}**\n")
        header = self.rows[0]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        for row in self.rows[1:]:
            # Pad row to header length
            padded = row + [""] * (len(header) - len(row))
            lines.append("| " + " | ".join(padded[:len(header)]) + " |")
        return "\n".join(lines)


@dataclass
class Section:
    number: str
    title: str
    text: str
    tables: list[Table] = field(default_factory=list)
    page_start: int = 0
    page_end: int = 0
    level: int = 1


@dataclass
class ParsedDocument:
    title: str
    document_id: str  # e.g. "ГОСТ 2.104-2006", "ПУЭ гл. 1.7"
    sections: list[Section] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "document_id": self.document_id,
            "metadata": self.metadata,
            "sections": [
                {
                    "number": s.number,
                    "title": s.title,
                    "text": s.text,
                    "level": s.level,
                    "page_start": s.page_start,
                    "page_end": s.page_end,
                    "tables": [
                        {
                            "rows": t.rows,
                            "page": t.page,
                            "caption": t.caption,
                            "markdown": t.to_markdown(),
                        }
                        for t in s.tables
                    ],
                }
                for s in self.sections
            ],
        }


# Common section numbering patterns in Russian standards
_SECTION_RE = re.compile(
    r"^(\d+(?:\.\d+)*\.?)\s+(.+)$", re.MULTILINE
)

# Table caption pattern: "Таблица 1", "Table 4.1", "Таблица А.1"
_TABLE_CAPTION_RE = re.compile(
    r"(?:Таблица|Table)\s+([\w.]+)(?:\s*[—–-]\s*(.+))?", re.IGNORECASE
)


class StandardsPDFParser:
    """Parses a standards PDF into structured sections with tables."""

    def __init__(self, pdf_path: str | Path):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {self.pdf_path}")

    def parse(
        self,
        document_id: str = "",
        title: str = "",
        metadata: dict | None = None,
    ) -> ParsedDocument:
        """Parse the PDF and return a structured document."""
        text_pages = self._extract_text_pages()
        tables = self._extract_tables()
        sections = self._split_sections(text_pages)
        self._assign_tables(sections, tables)

        if not title:
            title = self._detect_title(text_pages)
        if not document_id:
            document_id = self._detect_document_id(text_pages)

        return ParsedDocument(
            title=title,
            document_id=document_id,
            sections=sections,
            metadata=metadata or {},
        )

    def _extract_text_pages(self) -> list[tuple[int, str]]:
        """Extract text from each page using pymupdf."""
        import fitz  # pymupdf

        pages: list[tuple[int, str]] = []
        with fitz.open(str(self.pdf_path)) as doc:
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                pages.append((page_num + 1, text))
        return pages

    def _extract_tables(self) -> list[Table]:
        """Extract tables using pdfplumber (better at table detection)."""
        tables: list[Table] = []
        try:
            import pdfplumber
        except ImportError:
            logger.warning("pdfplumber not installed — table extraction disabled")
            return tables

        with pdfplumber.open(str(self.pdf_path)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_tables = page.extract_tables()
                if not page_tables:
                    continue
                for raw_table in page_tables:
                    if not raw_table or len(raw_table) < 2:
                        continue
                    rows = []
                    for row in raw_table:
                        cleaned = [
                            (cell or "").strip().replace("\n", " ")
                            for cell in row
                        ]
                        rows.append(cleaned)
                    caption = self._find_table_caption(page, raw_table)
                    tables.append(Table(rows=rows, page=page_num, caption=caption))
        return tables

    def _find_table_caption(self, page, raw_table) -> str:
        """Try to find table caption from text above the table."""
        text = page.extract_text() or ""
        match = _TABLE_CAPTION_RE.search(text)
        if match:
            num = match.group(1)
            desc = match.group(2) or ""
            return f"Таблица {num}" + (f" — {desc.strip()}" if desc else "")
        return ""

    def _split_sections(
        self, text_pages: list[tuple[int, str]]
    ) -> list[Section]:
        """Split concatenated text into sections by numbered headings."""
        full_text = ""
        page_offsets: list[tuple[int, int]] = []  # (page_num, char_offset)
        for page_num, text in text_pages:
            page_offsets.append((page_num, len(full_text)))
            full_text += text + "\n"

        def _page_at(char_pos: int) -> int:
            result = 1
            for pn, offset in page_offsets:
                if offset <= char_pos:
                    result = pn
            return result

        matches = list(_SECTION_RE.finditer(full_text))
        if not matches:
            # No numbered sections — treat entire document as one section
            return [
                Section(
                    number="",
                    title="",
                    text=full_text.strip(),
                    page_start=1,
                    page_end=text_pages[-1][0] if text_pages else 1,
                )
            ]

        sections: list[Section] = []
        for i, m in enumerate(matches):
            number = m.group(1).rstrip(".")
            title = m.group(2).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
            text = full_text[start:end].strip()
            level = number.count(".") + 1

            sections.append(
                Section(
                    number=number,
                    title=title,
                    text=text,
                    page_start=_page_at(m.start()),
                    page_end=_page_at(end),
                    level=level,
                )
            )
        return sections

    def _assign_tables(
        self, sections: list[Section], tables: list[Table]
    ) -> None:
        """Assign extracted tables to sections by page overlap."""
        for table in tables:
            best: Section | None = None
            for sec in sections:
                if sec.page_start <= table.page <= sec.page_end:
                    best = sec
                    break
            if best:
                best.tables.append(table)
            elif sections:
                # Attach to the last section before this page
                for sec in reversed(sections):
                    if sec.page_start <= table.page:
                        sec.tables.append(table)
                        break

    def _detect_title(self, pages: list[tuple[int, str]]) -> str:
        """Try to detect document title from first page."""
        if not pages:
            return self.pdf_path.stem
        first_page = pages[0][1]
        lines = [l.strip() for l in first_page.split("\n") if l.strip()]
        # Heuristic: first non-empty line that looks like a title
        for line in lines[:10]:
            if len(line) > 10 and not line.startswith("ГОСТ") and not line.startswith("СП"):
                return line
        return self.pdf_path.stem

    def _detect_document_id(self, pages: list[tuple[int, str]]) -> str:
        """Detect document ID like 'ГОСТ 2.104-2006' or 'IEC 60664-1'."""
        if not pages:
            return ""
        first_page = pages[0][1]
        patterns = [
            r"(ГОСТ\s+[\d.]+(?:-\d+)?)",
            r"(СП\s+[\d.]+(?:-\d+)?)",
            r"(IEC\s+[\d]+(?:-\d+)?)",
            r"(ПУЭ)",
        ]
        for pat in patterns:
            m = re.search(pat, first_page)
            if m:
                return m.group(1)
        return self.pdf_path.stem
