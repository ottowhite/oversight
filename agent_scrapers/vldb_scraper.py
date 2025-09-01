from typing import Set, Tuple
from cached_webpage_retriever import get_cached_webpage
from collections import namedtuple

# Create a named tuple for authors to make them hashable
Author = namedtuple('Author', ['Name', 'Affiliation'])

# Create a named tuple for papers to make them hashable
Paper = namedtuple('Paper', ['title', 'abstract', 'conference_link', 'pdf_link', 'session', 'authors', 'date', 'conference'])


def extract_papers(schedule_url: str) -> Set[Paper]:
    """Extract papers from the VLDB schedule webpage.

    Requirements:
    	- Use get_cached_webpage to get the webpage HTML
        - Put the output into BeautifulSoup to parse and explore the HTML
        - To retrieve the abstract, the conference_link will need to be retrieved, parsed with BeautifulSoup, and the abstract extracted from this page rather than the top-level schedule url. Everything else comes from the top-level schedule URL
        - Sometimes the "PDF" hyperlink, and the title hyperlink are switched positions, but the link formats will be like these examples which you can use to distinguish which is which
            conference_link="https://vldb.org/pvldb/volumes/18/paper/Ursa%3A%20A%20Lakehouse-Native%20Data%20Streaming%20Engine%20for%20Kafka"
            pdf_link="https://www.vldb.org/pvldb/vol18/p5184-guo.pdf"
        - Hard code conference name "VLDB"
        - Hard code conference date "2025-09-01"
    
    Args:
        schedule_url: URL of the VLDB schedule page
        
    Returns:
        Set of Paper objects extracted from the webpage
    """
    # TODO: Implement paper extraction logic
    return set()


vldb_schedule_link: str = "https://vldb.org/2025/?program-schedule-2025"
    
if __name__ == "__main__":
    print(get_cached_webpage(vldb_schedule_link))

