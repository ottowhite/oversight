from typing import Set, Tuple, List, Dict
from cached_webpage_retriever import get_cached_webpage
from collections import namedtuple
from bs4 import BeautifulSoup
import re
import json
from typing import Any

# Create a named tuple for authors to make them hashable
Author = namedtuple('Author', ['Name', 'Affiliation'])

# Create a named tuple for papers to make them hashable
Paper = namedtuple('Paper', ['title', 'abstract', 'conference_link', 'pdf_link', 'session', 'authors', 'date', 'conference'])

# Create a named tuple for tracking skipped papers
SkippedPaper = namedtuple('SkippedPaper', ['element_text', 'session', 'links_found', 'title', 'conference_link', 'pdf_link', 'authors', 'reason', 'error_details'])


def extract_papers(schedule_url: str) -> Set[Paper]:
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
        Set of Paper objects extracted from the webpage
    """
    # Get the webpage HTML
    html_content = get_cached_webpage(schedule_url)
    soup = BeautifulSoup(html_content, 'html.parser')
    
    papers = set()
    skipped_papers = []
    current_session = ""
    
    # Find all session headers and paper entries
    all_elements = soup.find_all(['h3', 'h4', 'h5', 'strong'])
    
    for element in all_elements:
        element_text = element.get_text().strip()
        
        # Check if this is a session header
        if hasattr(element, 'name') and element.name in ['h3', 'h4', 'h5'] and any(keyword in element_text for keyword in ['Research', 'Industry', 'Panel', 'Tutorial', 'Demo']):  # type: ignore
            current_session = element_text
            continue
        
        # Check if this is a paper entry (strong tag with links)
        if hasattr(element, 'name') and element.name == 'strong':  # type: ignore
            links = element.find_all('a', href=True) if hasattr(element, 'find_all') else []  # type: ignore
            
            # Track potential paper data for error reporting
            title = ""
            conference_link = ""
            pdf_link = ""
            authors = []
            skip_reason = ""
            error_details = ""
            
            # Check if we have enough links
            if len(links) < 2:
                skip_reason = "Insufficient links"
                error_details = f"Found {len(links)} links, expected at least 2"
                skipped_papers.append(SkippedPaper(
                    element_text=element_text,
                    session=current_session,
                    links_found=[link.get('href', '') if hasattr(link, 'get') else '' for link in links],  # type: ignore
                    title="",
                    conference_link="",
                    pdf_link="",
                    authors=[],
                    reason=skip_reason,
                    error_details=error_details
                ))
                continue
            
            try:
                # Extract links and determine which is which
                for link in links:
                    href = link.get('href', '') if hasattr(link, 'get') else ''  # type: ignore
                    link_text = link.get_text().strip() if hasattr(link, 'get_text') else ''
                    
                    # Distinguish between conference link and PDF link
                    if href and 'vldb.org/pvldb/volumes' in str(href) and 'paper' in str(href):  # type: ignore
                        conference_link = href
                        if link_text == "PDF":
                            # If link text is "PDF", we need to find the title elsewhere
                            pass
                        else:
                            title = link_text
                    elif href and 'vldb.org/pvldb/vol' in str(href) and '.pdf' in str(href):  # type: ignore
                        pdf_link = href
                        if link_text != "PDF":
                            title = link_text
                
                # If we still don't have a title, extract it from the element text
                if not title:
                    # Remove "PDF" and extract the remaining text as title
                    title = element_text.replace("PDF", "").strip()
                
                # Extract authors from the next paragraph
                next_element = element.next_sibling
                while next_element:
                    if hasattr(next_element, 'name') and next_element.name == 'p':  # type: ignore
                        author_text = next_element.get_text().strip()
                        if author_text:
                            # Parse authors - format: "Name (Affiliation);Name (Affiliation);..."
                            author_entries = author_text.split(';')
                            for author_entry in author_entries:
                                author_entry = author_entry.strip()
                                if '(' in author_entry and ')' in author_entry:
                                    name = author_entry.split('(')[0].strip()
                                    affiliation = author_entry.split('(')[1].split(')')[0].strip()
                                    authors.append(Author(Name=name, Affiliation=affiliation))
                        break
                    next_element = next_element.next_sibling
                
                # Validate required fields
                missing_fields = []
                if not conference_link:
                    missing_fields.append("conference_link")
                if not pdf_link:
                    missing_fields.append("pdf_link")
                if not title:
                    missing_fields.append("title")
                if not current_session:
                    missing_fields.append("current_session")
                
                if missing_fields:
                    skip_reason = "Missing required fields"
                    error_details = f"Missing: {', '.join(missing_fields)}"
                    skipped_papers.append(SkippedPaper(
                        element_text=element_text,
                        session=current_session,
                        links_found=[link.get('href', '') if hasattr(link, 'get') else '' for link in links],  # type: ignore
                        title=title,
                        conference_link=conference_link,
                        pdf_link=pdf_link,
                        authors=authors,
                        reason=skip_reason,
                        error_details=error_details
                    ))
                    continue
                
                # Try to extract the abstract
                try:
                    abstract = extract_abstract_from_conference_page(str(conference_link))
                except Exception as e:
                    # Still create the paper but note the abstract extraction failed
                    abstract = ""
                    print(f"Warning: Failed to extract abstract for '{title}': {e}")
                
                # Create the paper
                paper = Paper(
                    title=title,
                    abstract=abstract,
                    conference_link=conference_link,
                    pdf_link=pdf_link,
                    session=current_session,
                    authors=tuple(authors),
                    date="2025-09-01",
                    conference="VLDB"
                )
                papers.add(paper)
                
            except Exception as e:
                skip_reason = "Processing error"
                error_details = str(e)
                skipped_papers.append(SkippedPaper(
                    element_text=element_text,
                    session=current_session,
                    links_found=[link.get('href', '') if hasattr(link, 'get') else '' for link in links] if links else [],
                    title=title,
                    conference_link=conference_link,
                    pdf_link=pdf_link,
                    authors=authors,
                    reason=skip_reason,
                    error_details=error_details
                ))
    
    # Print detailed summary
    print(f"\n=== PAPER EXTRACTION SUMMARY ===")
    print(f"Successfully extracted: {len(papers)} papers")
    print(f"Skipped/Errored: {len(skipped_papers)} papers")
    
    if skipped_papers:
        print(f"\n=== DETAILED SKIPPED PAPERS REPORT ===")
        
        # Group by reason for better readability
        reasons_count: Dict[str, int] = {}
        for skipped in skipped_papers:
            reasons_count[skipped.reason] = reasons_count.get(skipped.reason, 0) + 1
        
        print(f"\nSkipped papers by reason:")
        for reason, count in reasons_count.items():
            print(f"  - {reason}: {count} papers")
        
        print(f"\nDetailed information for each skipped paper:")
        for i, skipped in enumerate(skipped_papers, 1):
            print(f"\n--- Skipped Paper #{i} ---")
            print(f"Reason: {skipped.reason}")
            print(f"Error Details: {skipped.error_details}")
            print(f"Session: {skipped.session or 'Unknown'}")
            print(f"Element Text: {skipped.element_text[:100]}{'...' if len(skipped.element_text) > 100 else ''}")
            print(f"Title Found: {skipped.title or 'None'}")
            print(f"Conference Link: {skipped.conference_link or 'None'}")
            print(f"PDF Link: {skipped.pdf_link or 'None'}")
            print(f"Authors Found: {len(skipped.authors)} authors")
            print(f"Links Found: {len(skipped.links_found)} - {skipped.links_found}")
    
    return papers


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
        print(f"Error extracting abstract from {conference_url}: {e}")
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
            {"Name": author.Name, "Affiliation": author.Affiliation}
            for author in getattr(paper, "authors", [])
        ],
        "date": paper.date,
        "conference": paper.conference,
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
    
if __name__ == "__main__":
    vldb_schedule_link: str = "https://vldb.org/2025/?program-schedule-2025"
    output_filename = "data/vldb/vldb_25_papers.json"

    papers = extract_papers(vldb_schedule_link)
    # Save papers to JSON
    save_papers_to_json(papers, output_filename)
    print(f"Saved {len(papers)} papers to {output_filename}")


    test_json_file_valid(output_filename)

