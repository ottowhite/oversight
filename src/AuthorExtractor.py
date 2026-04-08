from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuthorInfo:
    authors: list[str] = field(default_factory=list)
    institutions: list[str] = field(default_factory=list)


_USENIX_SOURCES = {"OSDI", "NSDI", "ATC"}
_PARENTHETICAL_SOURCES = {"SOSP", "ASPLOS", "EuroSys"}


def extract_authors(document: dict[str, Any], source: str | None) -> AuthorInfo:
    """Extract authors and unique institutions from a paper document.

    Handles all paper types: ArXiv, OpenReview (ICLR/NeurIPS/ICML),
    VLDB, MLSys, USENIX (OSDI/NSDI/ATC), and parenthetical (SOSP/ASPLOS/EuroSys).
    """
    if source == "arxiv":
        return _extract_arxiv(document)
    if source in ("ICLR", "NeurIPS", "ICML"):
        return _extract_openreview(document)
    if source == "VLDB":
        return _extract_vldb(document)
    if source == "MLSys":
        return _extract_mlsys(document)

    raw = document.get("authors")
    if raw is None:
        return AuthorInfo()
    if isinstance(raw, list):
        return _extract_vldb(document)
    if not isinstance(raw, str):
        return AuthorInfo()

    # Route known sources directly to the right parser
    if source in _USENIX_SOURCES:
        return _extract_usenix(raw)
    if source in _PARENTHETICAL_SOURCES:
        return _extract_parenthetical(raw)

    # Unknown source — detect format from the string
    if ";" in raw:
        return _extract_usenix(raw)
    if re.search(r"\([^)]+\)", raw):
        return _extract_parenthetical(raw)

    # Fallback: treat as comma-separated names
    return _extract_comma_names(raw)


def _extract_arxiv(document: dict[str, Any]) -> AuthorInfo:
    """ArXiv: authors is a comma-separated string in arXivRaw."""
    raw = document.get("metadata", {}).get("arXivRaw", {}).get("authors", "")
    if not raw:
        return AuthorInfo()
    return _extract_comma_names(raw)


def _extract_comma_names(raw: str) -> AuthorInfo:
    """Parse a comma-and-and-separated name list like 'A, B, and C'."""
    # Replace " and " with comma for uniform splitting
    normalized = re.sub(r"\s+and\s+", ", ", raw)
    names = [n.strip() for n in normalized.split(",") if n.strip()]
    return AuthorInfo(authors=names)


def _extract_openreview(document: dict[str, Any]) -> AuthorInfo:
    """OpenReview (ICLR/NeurIPS/ICML): content.authors is a list or content.authors.value."""
    content = document.get("content", {})
    authors_field = content.get("authors")
    if authors_field is None:
        return AuthorInfo()
    # API v2: {"value": [...]}
    if isinstance(authors_field, dict):
        authors_field = authors_field.get("value", [])
    if isinstance(authors_field, list):
        return AuthorInfo(authors=[str(a) for a in authors_field])
    return AuthorInfo()


def _extract_vldb(document: dict[str, Any]) -> AuthorInfo:
    """VLDB: authors is a list of {"Name": str, "Affiliation": str}."""
    raw = document.get("authors", [])
    if not isinstance(raw, list):
        return AuthorInfo()
    authors = []
    institutions = []
    seen_institutions: set[str] = set()
    for entry in raw:
        if isinstance(entry, dict):
            name = entry.get("Name", "").strip()
            affil = entry.get("Affiliation", "").strip()
            if name:
                authors.append(name)
            if affil and affil not in seen_institutions:
                seen_institutions.add(affil)
                institutions.append(affil)
    return AuthorInfo(authors=authors, institutions=institutions)


def _extract_mlsys(document: dict[str, Any]) -> AuthorInfo:
    """MLSys: middle-dot-separated string or OpenReview format."""
    raw = document.get("authors", "")
    if isinstance(raw, str) and "·" in raw:
        names = [n.strip() for n in raw.split("·") if n.strip()]
        return AuthorInfo(authors=names)
    # Fallback to OpenReview format (newer MLSys papers)
    return _extract_openreview(document)


def _extract_usenix(raw: str) -> AuthorInfo:
    """USENIX (OSDI/NSDI/ATC): 'Name1 and Name2,Affiliation;Name3,Affil'."""
    authors = []
    institutions = []
    seen_institutions: set[str] = set()

    groups = raw.split(";")
    for group in groups:
        group = group.strip()
        if not group:
            continue

        names_part, affil = _split_usenix_group(group)
        name_list = _split_names(names_part)
        authors.extend(name_list)

        if affil and affil not in seen_institutions:
            seen_institutions.add(affil)
            institutions.append(affil)

    return AuthorInfo(authors=authors, institutions=institutions)


def _split_usenix_group(group: str) -> tuple[str, str]:
    """Split a USENIX author group into (names_part, affiliation).

    Formats handled:
      - "Name1, Name2, and Name3,Affiliation" (Oxford comma + and)
      - "Name1 and Name2,Affiliation" (two authors)
      - "Name,Affiliation" (single author)
      - "Name,Affil with and in it" (and in affiliation)
    """
    # Case 1: Oxford comma style — ", and " always connects names
    if ", and " in group:
        idx = group.rfind(", and ")
        after_and = idx + len(", and ")
        comma_pos = group.find(",", after_and)
        if comma_pos == -1:
            return group, ""
        return group[:comma_pos].strip(), group[comma_pos + 1 :].strip()

    # Case 2: " and " present — check if it connects names or is in affiliation
    if " and " in group:
        and_idx = group.index(" and ")
        text_before_and = group[:and_idx]
        if "," not in text_before_and:
            # No comma before "and" → two-author format: "Name1 and Name2,Affil"
            after_and = and_idx + len(" and ")
            comma_pos = group.find(",", after_and)
            if comma_pos == -1:
                return group, ""
            return group[:comma_pos].strip(), group[comma_pos + 1 :].strip()
        else:
            # Comma exists before "and" → "and" is in affiliation text
            comma_pos = group.index(",")
            return group[:comma_pos].strip(), group[comma_pos + 1 :].strip()

    # Case 3: No "and" — single author, first comma separates
    comma_pos = group.find(",")
    if comma_pos == -1:
        return group, ""
    return group[:comma_pos].strip(), group[comma_pos + 1 :].strip()


def _extract_parenthetical(raw: str) -> AuthorInfo:
    """Parenthetical: 'Name1 (Affil1), Name2 (Affil2)'."""
    authors = []
    institutions = []
    seen_institutions: set[str] = set()

    # Split on ), which ends each author entry
    # Pattern: "Name (Affiliation)" possibly followed by comma
    pattern = re.compile(r"([^(,]+?)\s*\(([^)]+)\)")
    for match in pattern.finditer(raw):
        name = match.group(1).strip().lstrip(",").strip()
        affil = match.group(2).strip()

        # Handle "AND" in names from SOSP format
        if " AND " in name:
            name = name.replace(" AND ", " and ")

        if name:
            authors.append(name)
        if affil and affil not in seen_institutions:
            seen_institutions.add(affil)
            institutions.append(affil)

    return AuthorInfo(authors=authors, institutions=institutions)


def _split_names(names_part: str) -> list[str]:
    """Split a names string like 'A, B, and C' into individual names."""
    # Replace " and " with comma
    normalized = re.sub(r",?\s+and\s+", ", ", names_part)
    return [n.strip() for n in normalized.split(",") if n.strip()]
