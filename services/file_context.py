from io import StringIO
import io
from pathlib import Path

import numpy as np
import pandas as pd
from pypdf import PdfReader


ALLOWED_FILE_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".py",
    ".js",
    ".html",
    ".css",
    ".pdf",
}


def is_allowed_file(filename: str) -> bool:
    """Check whether a file is supported as text context."""
    return Path(filename).suffix.lower() in ALLOWED_FILE_EXTENSIONS


def build_csv_summary(text: str) -> str:
    """Build a compact Pandas summary for uploaded CSV files."""
    df = pd.read_csv(StringIO(text))
    lines = [
        f"Rows: {len(df)}",
        f"Columns: {len(df.columns)}",
        "Column names: " + ", ".join(str(col) for col in df.columns),
    ]

    missing = df.isna().sum()
    missing = missing[missing > 0].sort_values(ascending=False)
    if missing.empty:
        lines.append("Missing values: none")
    else:
        lines.append(
            "Missing values: "
            + ", ".join(f"{column}={count}" for column, count in missing.items())
        )

    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.empty:
        lines.append("Numeric columns: none")
    else:
        lines.append("Numeric summary:")
        summary = numeric_df.agg(["mean", "min", "max"]).round(2)
        for column in summary.columns[:8]:
            lines.append(
                f"- {column}: mean={summary.at['mean', column]}, "
                f"min={summary.at['min', column]}, max={summary.at['max', column]}"
            )

    return "\n".join(lines)


def extract_pdf_text(raw: bytes) -> str:
    """Extract text from an uploaded PDF."""
    reader = PdfReader(io.BytesIO(raw))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        page_text = page_text.strip()
        if page_text:
            pages.append(f"[Page {index}]\n{page_text}")

    return "\n\n".join(pages).strip()
