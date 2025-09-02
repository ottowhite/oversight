from typing import Set, Tuple, List, Dict, Any, cast
try:
    from .cached_webpage_retriever import get_cached_webpage
except ImportError:
    from cached_webpage_retriever import get_cached_webpage
from bs4 import BeautifulSoup, Tag, ResultSet
import re
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Author:
    """Represents a paper author with name and affiliation."""
    name: str
    affiliation: str
    
    def __str__(self) -> str:
        return f"{self.name} ({self.affiliation})"


@dataclass(frozen=True)
class Paper:
    """Represents a research paper with all its metadata."""
    title: str
    abstract: str
    conference_link: str
    pdf_link: str
    session: str
    authors: Tuple[Author, ...]
    date: str
    conference: str
    flags: Tuple[str, ...] = tuple()
    
    def __str__(self) -> str:
        authors_str = "; ".join(str(author) for author in self.authors)
        return (
            f"Paper: {self.title}\n"
            f"  Authors: {authors_str}\n"
            f"  Session: {self.session}\n"
            f"  Conference: {self.conference} ({self.date})\n"
            f"  Abstract: {self.abstract}\n"
            f"  Conference: {self.conference_link}\n"
            f"  PDF: {self.pdf_link}\n"
        )


@dataclass(frozen=True)
class SkippedPaper:
    """Represents a paper that couldn't be processed, with error details."""
    paper: Paper
    element_text: str
    links_found: List[str]
    reason: str
    error_details: str
    
    def __str__(self) -> str:
        element_preview = self.element_text[:50] + "..." if len(self.element_text) > 50 else self.element_text
        return (
            f"Skipped Paper: {self.paper.title or 'Unknown Title'}\n"
            f"  Reason: {self.reason}\n"
            f"  Error: {self.error_details}\n"
            f"  Session: {self.paper.session or 'Unknown'}\n"
            f"  Element: {element_preview}\n"
            f"  Links found: {len(self.links_found)} - {self.links_found}\n"
            f"  Paper data: {self.paper}"
        )


def extract_papers(schedule_url: str) -> Tuple[Set[Paper], List[SkippedPaper]]:
    """Extract papers from the VLDB schedule webpage.

    Requirements:
    	- Use get_cached_webpage to get the webpage HTML
        - Put the output into BeautifulSoup to parse and explore the HTML
        - To retrieve the abstract, the conference_link will need to be retrieved, parsed with BeautifulSoup, and the abstract extracted from this page rather than the top-level schedule url. Everything else comes from the top-level schedule URL
        - Sometimes the "PDF" hyperlink, and the title hyperlink are switched positions, but the link formats will be like these examples which you can use to distinguish which is which
            conference_link="https://vldb.org/pvldb/volumes/18/paper/Ursa%3A%20A%20Lakehouse-Native%20Data%20Streaming%20Engine%20for%20Kafka"
            pdf_link="https://www.vldb.org/pvldb/vol18/p5184-guo.pdf"
        - You may need to strip whitespace from the retrieved data
        - Hard code conference name "VLDB"
        - Hard code conference date "2025-09-01"
    
    Args:
        schedule_url: URL of the VLDB schedule page
        
    Returns:
        Tuple of (Set of Paper objects extracted from the webpage, List of SkippedPaper objects)
    """
    # Get the webpage HTML
    html_content = get_cached_webpage(schedule_url)
    soup = BeautifulSoup(html_content, 'html.parser')
    
    papers = set()
    skipped_papers = []
    current_session = ""
    
    # Process all schedule-head divs which contain the sessions and their papers
    schedule_divs = soup.find_all('div', class_='schedule-head')
    
    for schedule_div in schedule_divs:
        # Extract session name from h3 element (ensure we have a Tag)
        if not isinstance(schedule_div, Tag):
            continue
            
        h3_element = schedule_div.find('h3')
        current_session = h3_element.get_text().strip() if h3_element and isinstance(h3_element, Tag) else "Unknown Session"
        
        # Find all strong elements (papers) within this schedule div
        paper_elements = schedule_div.find_all('strong')
        
        for element in paper_elements:
            element_text = element.get_text().strip()
            
            # All elements here are already strong tags, so process directly
            links = element.find_all('a', href=True) if isinstance(element, Tag) else []
            
            # Track potential paper data for error reporting
            title = ""
            conference_link = ""
            pdf_link = ""
            authors = []
            skip_reason = ""
            error_details = ""
            
            # Check if we have enough links - skip only if no links found
            if len(links) == 0:
                skip_reason = "No links found"
                error_details = f"Found {len(links)} links, expected at least 1"
                # Create a partial paper with available data
                partial_paper = Paper(
                    title="",
                    abstract="",
                    conference_link="",
                    pdf_link="",
                    session=current_session,
                    authors=tuple([]),
                    date="2025-09-01",
                    conference="VLDB"
                )
                skipped_papers.append(SkippedPaper(
                    paper=partial_paper,
                    element_text=element_text,
                    links_found=[str(link.get('href', '')) if isinstance(link, Tag) else '' for link in links],
                    reason=skip_reason,
                    error_details=error_details
                ))
                continue
            
            try:
                # Extract links and determine which is which
                # Two patterns exist:
                # Pattern 1: Conference link with round-button class (volumes URL) + PDF link (.pdf URL)
                # Pattern 2: PDF link with round-button class (.pdf URL) + Conference link (volumes URL)
                for link in links:
                    if isinstance(link, Tag):
                        href = str(link.get('href', ''))
                        link_text = link.get_text().strip()
                        has_round_button_class = 'round-button' in str(link.get('class', ''))
                    else:
                        href = ''
                        link_text = ''
                        has_round_button_class = False
                    
                    # Determine link type by URL pattern, not just class
                    if href and '.pdf' in str(href) and 'vldb.org/pvldb/vol' in str(href):
                        # This is a PDF link (actual PDF file)
                        pdf_link = href
                        # If the text is not "PDF", it might be the title
                        if link_text and link_text != "PDF":
                            title = link_text
                    elif href and 'vldb.org/pvldb/volumes' in str(href) and 'paper' in str(href):
                        # This is a conference link (paper page)
                        conference_link = href
                        # If the text is not "PDF", it's the title
                        if link_text and link_text != "PDF":
                            title = link_text
                
                # If we still don't have a title, extract it from the element text
                if not title:
                    # Remove "PDF" and extract the remaining text as title
                    title = element_text.replace("PDF", "").strip()
                
                # Extract authors from the next paragraph after the strong element
                next_element = element.next_sibling
                while next_element:
                    if isinstance(next_element, Tag) and next_element.name == 'p':
                        author_text = next_element.get_text().strip()
                        if author_text:
                            # Parse authors - format: "Name (Affiliation);Name (Affiliation);..."
                            author_entries = author_text.split(';')
                            for author_entry in author_entries:
                                author_entry = author_entry.strip()
                                if '(' in author_entry and ')' in author_entry:
                                    name = author_entry.split('(')[0].strip()
                                    affiliation = author_entry.split('(')[1].split(')')[0].strip()
                                    authors.append(Author(name=name, affiliation=affiliation))
                        break
                    next_element = next_element.next_sibling
                
                # Validate required fields - only skip if title or session is missing, or both links are missing
                critical_missing_fields = []
                if not title:
                    critical_missing_fields.append("title")
                if not current_session:
                    critical_missing_fields.append("current_session")
                
                # Check if both links are missing (this should skip the paper)
                if not conference_link and not pdf_link:
                    critical_missing_fields.append("both conference_link and pdf_link")
                
                if critical_missing_fields:
                    skip_reason = "Missing critical fields"
                    error_details = f"Missing: {', '.join(critical_missing_fields)}"
                    # Create a partial paper with available data
                    partial_paper = Paper(
                        title=title or "",
                        abstract="",
                        conference_link=str(conference_link),
                        pdf_link=str(pdf_link),
                        session=current_session,
                        authors=tuple(authors),
                        date="2025-09-01",
                        conference="VLDB"
                    )
                    skipped_papers.append(SkippedPaper(
                        paper=partial_paper,
                        element_text=element_text,
                        links_found=[str(link.get('href', '')) if isinstance(link, Tag) else '' for link in links],
                        reason=skip_reason,
                        error_details=error_details
                    ))
                    continue
                
                # Try to extract the abstract (only if we have conference link)
                abstract = ""
                if conference_link:
                    try:
                        abstract = extract_abstract_from_conference_page(str(conference_link))
                    except Exception as e:
                        print(f"Warning: Failed to extract abstract for '{title}': {e}")
                
                # Create flags for any issues
                flags = []
                
                # Flag missing links
                if not conference_link:
                    flags.append("Missing conference link")
                    # print(f"🚩 FLAGGED: Paper '{title}' is missing the conference link (conference page URL)")
                
                if not pdf_link:
                    flags.append("Missing PDF link")
                    # print(f"🚩 FLAGGED: Paper '{title}' is missing the PDF link (direct PDF URL)")
                
                # Flag empty abstract
                if not abstract or abstract.strip() == "":
                    flags.append("Empty or missing abstract")
                    # print(f"🚩 FLAGGED: Paper '{title}' has an empty or missing abstract - no content could be extracted from the conference page")
                
                # Create the paper (with flags if any)
                paper = Paper(
                    title=title,
                    abstract=abstract,
                    conference_link=str(conference_link),
                    pdf_link=str(pdf_link),
                    session=current_session,
                    authors=tuple(authors),
                    date="2025-09-01",
                    conference="VLDB",
                    flags=tuple(flags)
                )
                papers.add(paper)
                
            except Exception as e:
                skip_reason = "Processing error"
                error_details = str(e)
                # Create a partial paper with available data
                partial_paper = Paper(
                    title=title or "",
                    abstract="",
                    conference_link=str(conference_link),
                    pdf_link=str(pdf_link),
                    session=current_session,
                    authors=tuple(authors),
                    date="2025-09-01",
                    conference="VLDB"
                )
                skipped_papers.append(SkippedPaper(
                    paper=partial_paper,
                    element_text=element_text,
                    links_found=[str(link.get('href', '')) if isinstance(link, Tag) else '' for link in links] if links else [],
                    reason=skip_reason,
                    error_details=error_details
                ))
    
    # Count flagged papers
    flagged_papers = [paper for paper in papers if paper.flags]
    
    # Print detailed summary
    if False:
        print(f"\n=== PAPER EXTRACTION SUMMARY ===")
        print(f"Successfully extracted: {len(papers)} papers")
        print(f"  - Clean papers (no issues): {len(papers) - len(flagged_papers)} papers")
        print(f"  - Flagged papers (with issues): {len(flagged_papers)} papers")
        print(f"Skipped/Errored: {len(skipped_papers)} papers")
    
    if flagged_papers and False:
        print(f"\n=== FLAGGED PAPERS SUMMARY ===")
        flag_counts: Dict[str, int] = {}
        for paper in flagged_papers:
            for flag in paper.flags:
                flag_counts[flag] = flag_counts.get(flag, 0) + 1
        
        print(f"Papers with issues by type:")
        for flag_type, count in flag_counts.items():
            print(f"  - {flag_type}: {count} papers")
        
        print(f"\nDetailed flagged papers:")
        for i, paper in enumerate(flagged_papers, 1):
            flags_str = ", ".join(paper.flags)
            print(f"  {i}. '{paper.title}' - Issues: {flags_str}")
            print(f"     Session: {paper.session}")
            print(f"     Conference Link: {'✓' if paper.conference_link else '✗'}")
            print(f"     PDF Link: {'✓' if paper.pdf_link else '✗'}")
            print(f"     Abstract: {'✓' if paper.abstract else '✗'}")
            print()
    
    if skipped_papers and False:
        print(f"\n=== SKIPPED/ERRORED PAPERS SUMMARY ===")
        
        # Group by reason for better readability
        reasons_count: Dict[str, int] = {}
        for skipped in skipped_papers:
            reasons_count[skipped.reason] = reasons_count.get(skipped.reason, 0) + 1
        
        print(f"Skipped papers by reason:")
        for reason, count in reasons_count.items():
            print(f"  - {reason}: {count} papers")
        
        print(f"\nDetailed skipped papers:")
        for i, skipped in enumerate(skipped_papers, 1):
            title = skipped.paper.title or "Unknown Title"
            print(f"  {i}. '{title}' - Reason: {skipped.reason}")
            print(f"     Session: {skipped.paper.session or 'Unknown'}")
            print(f"     Error: {skipped.error_details}")
            print(f"     Conference Link: {'✓' if skipped.paper.conference_link else '✗'}")
            print(f"     PDF Link: {'✓' if skipped.paper.pdf_link else '✗'}")
            print(f"     Authors Found: {len(skipped.paper.authors)} authors")
            print(f"     Links Found: {len(skipped.links_found)} - {skipped.links_found[:2]}{'...' if len(skipped.links_found) > 2 else ''}")
            if skipped.element_text and len(skipped.element_text.strip()) > 0:
                element_preview = skipped.element_text[:80] + "..." if len(skipped.element_text) > 80 else skipped.element_text
                print(f"     Element Text: {element_preview}")
            print()
    
    return papers, skipped_papers


def extract_abstract_from_conference_page(conference_url: str) -> str:
    """Extract abstract from a conference paper page."""
    try:
        html_content = get_cached_webpage(conference_url)
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Look for abstract in various possible locations
        abstract_element = None
        
        # Common patterns for abstract sections
        abstract_patterns = [
            soup.find('div', {'class': 'abstract'}),
            soup.find('section', {'class': 'abstract'}),
            soup.find('p', {'class': 'abstract'}),
            soup.find('div', {'id': 'abstract'}),
        ]
        
        for pattern in abstract_patterns:
            if pattern:
                abstract_element = pattern
                break
        
        # If not found by class/id, look for text patterns
        if not abstract_element:
            # Look for "Abstract" header followed by content
            all_elements = soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'div'])
            for i, element in enumerate(all_elements):
                if element.get_text().strip().lower() in ['abstract', 'abstract:', 'abstract.']:
                    # Get the next element as the abstract
                    if i + 1 < len(all_elements):
                        abstract_element = all_elements[i + 1]
                        break
        
        if abstract_element:
            return abstract_element.get_text().strip()
        else:
            return ""
            
    except Exception as e:
        return ""



def paper_to_dict(paper: Any) -> dict:
    """Convert a Paper object to a serializable dictionary."""
    return {
        "title": paper.title,
        "abstract": paper.abstract,
        "conference_link": paper.conference_link,
        "pdf_link": paper.pdf_link,
        "session": paper.session,
        "authors": [
            {"Name": author.name, "Affiliation": author.affiliation}
            for author in getattr(paper, "authors", [])
        ],
        "date": paper.date,
        "conference": paper.conference,
        "flags": list(getattr(paper, "flags", [])),
    }

def save_papers_to_json(papers, filename: str) -> None:
    """Save a set of Paper objects to a JSON file."""
    papers_list = [paper_to_dict(p) for p in papers]
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(papers_list, f, ensure_ascii=False, indent=2)

# Simple test: Check that the file exists and is valid JSON
def test_json_file_valid(filename: str) -> None:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list), "JSON root should be a list"
        print(f"Test passed: {filename} is valid JSON with {len(data)} entries.")
    except Exception as e:
        print(f"Test failed: Could not validate {filename}: {e}")
    
vldb_schedule_link: str = "https://vldb.org/2025/?program-schedule-2025"

if __name__ == "__main__":
    
    output_filename = "data/vldb/vldb_25_papers.json"

    papers, skipped_papers = extract_papers(vldb_schedule_link)
    # Save papers to JSON
    save_papers_to_json(papers, output_filename)
    print(f"Saved {len(papers)} papers to {output_filename}")
    print(f"Skipped {len(skipped_papers)} papers due to various issues")


    test_json_file_valid(output_filename)
