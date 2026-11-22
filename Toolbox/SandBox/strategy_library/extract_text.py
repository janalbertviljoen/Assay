"""Extract the text of every PDF in a snapshot folder with pypdf, one .txt per PDF.

Usage (repository root):
``.venv/bin/python -m Toolbox.SandBox.strategy_library.extract_text <pdf_dir> <txt_dir>``

Used for the library papers (``data/raw/library/<date>/papers`` to
``data/interim/library/<date>/papers``) and the MSCI index factsheets, whose
"Fundamentals" table (dividend yield, P/E, forward P/E, price/book) was read from the
text: the first row is the index itself, the next rows its comparison indices.
"""

import sys
from pathlib import Path

from pypdf import PdfReader

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.mkdir(parents=True, exist_ok=True)
for pdf in sorted(src.glob("*.pdf")):
    reader = PdfReader(pdf)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    (dst / f"{pdf.stem}.txt").write_text(text)
    print(f"{len(reader.pages):4} pages {len(text):8} chars  {pdf.name}")
