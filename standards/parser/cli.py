#!/usr/bin/env python3
"""CLI for parsing standards PDFs into JSONL chunks.

Usage:
    python -m standards.parser.cli /path/to/standard.pdf -o parsed/standard.jsonl
    python -m standards.parser.cli raw/ -o parsed/  # batch mode
"""

import argparse
import logging
import sys
from pathlib import Path

from .chunker import process_pdf


def main():
    parser = argparse.ArgumentParser(description="Parse standards PDFs into chunks")
    parser.add_argument("input", help="PDF file or directory of PDFs")
    parser.add_argument("-o", "--output", help="Output JSONL file or directory")
    parser.add_argument("--doc-id", default="", help="Document ID override")
    parser.add_argument("--title", default="", help="Title override")
    parser.add_argument("--chunk-size", type=int, default=1500)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    input_path = Path(args.input)

    if input_path.is_file():
        output = Path(args.output) if args.output else input_path.with_suffix(".jsonl")
        chunks = process_pdf(
            input_path,
            output_path=output,
            document_id=args.doc_id,
            title=args.title,
            chunk_size=args.chunk_size,
        )
        print(f"Parsed {input_path.name}: {len(chunks)} chunks -> {output}")

    elif input_path.is_dir():
        output_dir = Path(args.output) if args.output else input_path.parent / "parsed"
        output_dir.mkdir(parents=True, exist_ok=True)

        pdfs = sorted(input_path.glob("*.pdf"))
        if not pdfs:
            print(f"No PDF files found in {input_path}")
            sys.exit(1)

        total = 0
        for pdf in pdfs:
            out = output_dir / pdf.with_suffix(".jsonl").name
            try:
                chunks = process_pdf(pdf, output_path=out, chunk_size=args.chunk_size)
                total += len(chunks)
                print(f"  {pdf.name}: {len(chunks)} chunks")
            except Exception as e:
                print(f"  ERROR {pdf.name}: {e}", file=sys.stderr)

        print(f"\nTotal: {len(pdfs)} files, {total} chunks -> {output_dir}")
    else:
        print(f"Not found: {input_path}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
