#!/usr/bin/env python3
"""Extract paper abstracts from EuroSys26Proceedings.pdf into eurosys26.json.

Runs `pdftotext -layout` on the proceedings PDF, finds each paper by fuzzy
title match against the existing JSON, splits two-column pages at the
per-line whitespace gap, and emits an enriched JSON with abstracts filled in.
Pre-existing abstracts are preserved untouched.

Usage:
    python extract_eurosys26_abstracts.py \
        [PDF_PATH] [JSON_IN] [JSON_OUT]

Defaults assume the repo layout: PDF at the repo root, JSON under
data/systems_conferences/.
"""

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_PDF = REPO_ROOT / "EuroSys26Proceedings.pdf"
DEFAULT_JSON_IN = REPO_ROOT / "data/systems_conferences/eurosys26.json"
DEFAULT_JSON_OUT = REPO_ROOT / "data/systems_conferences/eurosys26-enriched.json"

SECTION_BREAK_PATTERNS = [
    re.compile(r"^\s*1\s+Introduction\s*$"),
    re.compile(r"^\s*1\s{2,}Introduction\s*$"),
    re.compile(r"^\s*Introduction\s*$"),
]
RIGHT_COL_TERMINATORS = re.compile(
    r"^\s*(CCS Concepts|Keywords|ACM Reference Format|1\s+Introduction|"
    r"References|Categories and Subject)"
)


def normalize_for_match(s: str) -> str:
    """Normalize text for fuzzy title matching."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def detect_column_boundary(lines: list[str]) -> int | None:
    """Find consistent right-column start position from a block of lines."""
    positions = []
    for line in lines[:30]:
        m = re.search(r"\S(\s{3,})\S", line.rstrip("\n"))
        if m:
            rstart = m.start(1) + len(m.group(1))
            positions.append(rstart)
    if not positions:
        return None
    counter = Counter(positions)
    most_common = counter.most_common(1)[0]
    if most_common[1] >= 3:
        return most_common[0]
    return positions[0] if positions else None


def is_section_break(line: str) -> bool:
    return any(p.match(line) for p in SECTION_BREAK_PATTERNS)


def join_hyphenated(text: str) -> str:
    """Join soft hyphenation across line breaks, skipping blank lines.

    Two-column extraction can leave a blank line between a hyphenated
    word's halves (when the right column is empty on the same row), so we
    look past blanks for a lowercase continuation before joining.
    """
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line:
            out.append("")
            i += 1
            continue
        while line.endswith("-") and i + 1 < len(lines):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines):
                break
            next_line = lines[j].lstrip()
            if next_line and next_line[0].islower():
                line = (line[:-1] + next_line).rstrip()
                i = j
            else:
                break
        out.append(line)
        i += 1
    return "\n".join(out)


CITATION_RE = re.compile(r"\[[\d,\s\u2013\u2014\-]+\]")


def strip_citations(text: str) -> str:
    """Remove numeric citation markers like [12], [3, 7], [10–14]."""
    text = CITATION_RE.sub("", text)
    # Tidy up whitespace and orphaned punctuation left behind by the strip.
    text = re.sub(r"\s+([.,;:!?\)])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    return text


def clean_text(text: str) -> str:
    text = join_hyphenated(text)
    text = re.sub(r"\s*\n\s*", " ", text)
    text = strip_citations(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_abstract_from_block(block_lines: list[str]) -> str | None:
    """Extract abstract from lines starting at an 'Abstract' heading."""
    if not block_lines:
        return None

    col_boundary = detect_column_boundary(block_lines)
    if col_boundary is None:
        col_boundary = 80

    left_lines = []
    right_lines = []
    gap_re = re.compile(r"\S(\s{3,})\S")
    for line in block_lines:
        m = gap_re.search(line)
        if m:
            split_at = m.start(1) + len(m.group(1))
            # Prefer the per-line gap, but only if it is at-or-before the
            # global boundary. Otherwise stick with the global boundary, in
            # case the line has additional gaps within the right column.
            if split_at <= col_boundary + 4:
                left_lines.append(line[: m.start(1) + 1].rstrip())
                right_lines.append(line[split_at:].rstrip())
                continue
        if len(line) > col_boundary:
            left_lines.append(line[:col_boundary].rstrip())
            right_lines.append(line[col_boundary:].rstrip())
        else:
            left_lines.append(line.rstrip())
            right_lines.append("")

    left_idx_start = 0
    if left_lines and left_lines[0].strip().startswith("Abstract"):
        left_idx_start = 1

    left_abstract = []
    for line in left_lines[left_idx_start:]:
        stripped = line.strip()
        if is_section_break(stripped):
            break
        if stripped.startswith("∗") or stripped.startswith("† "):
            break
        if stripped.startswith("This work is licensed"):
            break
        if RIGHT_COL_TERMINATORS.match(stripped):
            break
        left_abstract.append(line)

    right_abstract = []
    for line in right_lines:
        stripped = line.strip()
        if not stripped:
            if right_abstract:
                right_abstract.append("")
            continue
        if RIGHT_COL_TERMINATORS.match(stripped):
            break
        if is_section_break(stripped):
            break
        right_abstract.append(line)

    left_text = clean_text("\n".join(left_abstract))
    right_text = clean_text("\n".join(right_abstract))

    abstract = left_text
    if right_text:
        first_word = right_text.split()[0] if right_text.split() else ""
        if first_word and (
            first_word[0].islower()
            or first_word.startswith("by")
            or first_word.startswith("highlighting")
            or first_word.startswith("This")
            or first_word.startswith("We")
            or first_word.startswith("The")
        ):
            if first_word[0].islower() or not left_text.rstrip().endswith("."):
                abstract = (left_text + " " + right_text).strip()

    return abstract if abstract else None


STOPWORDS = {"a", "an", "the", "for", "of", "in", "with", "on", "to"}


def find_abstract_for_paper(text: str, title: str) -> str | None:
    """Find a paper's abstract in the layout text by searching for its title."""
    norm_title = normalize_for_match(title)
    title_words = norm_title.split()
    if len(title_words) < 3:
        return None

    lines = text.split("\n")
    norm_lines = [normalize_for_match(line) for line in lines]

    # Drop common stopwords from the prefix so e.g. "AIMS: A Cost-Efficient
    # Framework..." collapses to "aims cost efficient...", still matching the
    # PDF's title even when it omits the article ("AIMS: Cost-Efficient ...").
    distinctive_words = [w for w in title_words if w not in STOPWORDS]
    short_prefix = " ".join(distinctive_words[:3])

    matches = []
    for i in range(len(lines)):
        combined = " ".join(norm_lines[i : i + 4])
        if combined.startswith(norm_title) or norm_title in combined[: len(norm_title) + 50]:
            matches.append(i)

    # Also try the short prefix as additional candidates — titles can diverge
    # slightly between ACM metadata and the published PDF (e.g. "Authenticated
    # Storage" vs "Authenticated Archival Storage"), so the exact-title pass
    # can match only the TOC entry.
    for i in range(len(lines)):
        if i in matches:
            continue
        combined = " ".join(norm_lines[i : i + 3])
        combined_distinctive = " ".join(
            w for w in combined.split() if w not in STOPWORDS
        )
        if combined_distinctive.startswith(short_prefix) and len(combined_distinctive) > len(short_prefix):
            matches.append(i)

    for start_line in matches:
        for j in range(start_line + 1, min(start_line + 80, len(lines))):
            line = lines[j].rstrip()
            if line.strip() == "Abstract" or line.lstrip().startswith("Abstract  "):
                block = lines[j : j + 200]
                page_block = []
                for bl in block:
                    if "\f" in bl:
                        page_block.append(bl.split("\f")[0])
                        break
                    page_block.append(bl)
                abstract = extract_abstract_from_block(page_block)
                if abstract and len(abstract) > 100:
                    return abstract
    return None


def pdf_to_layout_text(pdf_path: Path) -> str:
    """Run pdftotext -layout and return the result."""
    if not pdf_path.exists():
        sys.exit(f"PDF not found: {pdf_path}")
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8", errors="replace")


def main(argv: list[str]) -> None:
    pdf = Path(argv[1]) if len(argv) > 1 else DEFAULT_PDF
    json_in = Path(argv[2]) if len(argv) > 2 else DEFAULT_JSON_IN
    json_out = Path(argv[3]) if len(argv) > 3 else DEFAULT_JSON_OUT

    with open(json_in) as f:
        papers = json.load(f)

    text = pdf_to_layout_text(pdf)

    filled = 0
    missing = 0
    for paper in papers:
        if paper.get("abstract"):
            continue
        title = paper["title"]
        abstract = find_abstract_for_paper(text, title)
        if abstract:
            paper["abstract"] = abstract
            filled += 1
        else:
            missing += 1
            print(f"MISS: {title}", file=sys.stderr)

    print(f"\nFilled: {filled}, still missing: {missing}", file=sys.stderr)

    with open(json_out, "w") as f:
        json.dump(papers, f, indent=2, ensure_ascii=False)
    print(f"Wrote {json_out}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv)
