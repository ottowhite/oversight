#!/usr/bin/env python3
"""
Test that the VLDB scraper works correctly with the encoding fix.
"""

from vldb_scraper import extract_papers, extract_abstract_from_conference_page
import json

def test_scraper_encoding():
    """Test that the scraper extracts content with correct encoding."""
    print("=== TESTING SCRAPER WITH ENCODING FIX ===\n")
    
    # Test abstract extraction from a specific paper
    paper_url = "https://vldb.org/pvldb/volumes/18/paper/Vortex%3A%20Overcoming%20Memory%20Capacity%20Limitations%20in%20GPU-Accelerated%20Large-Scale%20Data%20Analytics"
    
    print("Testing abstract extraction...")
    abstract = extract_abstract_from_conference_page(paper_url)
    
    if abstract:
        print(f"✅ Abstract extracted successfully ({len(abstract)} characters)")
        
        # Check for specific encoding issues
        if 'GPUâs' in abstract:
            print("❌ Found 'GPUâs' - encoding issue")
        elif "GPU's" in abstract or "GPUs'" in abstract:
            print("✅ Found correct GPU apostrophe")
        
        if '5.7 Ã' in abstract:
            print("❌ Found '5.7 Ã' - encoding issue")
        elif '5.7 ×' in abstract:
            print("✅ Found correct '5.7 ×'")
        
        # Show sample
        print(f"\nAbstract sample:")
        print(abstract[:200] + "..." if len(abstract) > 200 else abstract)
        
    else:
        print("❌ Failed to extract abstract")
    
    print("\n" + "-"*60)
    print("Testing small paper extraction...")
    
    # Test extracting just a few papers from the schedule
    schedule_url = "https://vldb.org/2025/?program-schedule-2025"
    
    try:
        # We'll test by fetching the first few papers
        from cached_webpage_retriever import get_cached_webpage
        from bs4 import BeautifulSoup
        
        html_content = get_cached_webpage(schedule_url)
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find first schedule div and extract one paper for testing
        schedule_divs = soup.find_all('div', class_='schedule-head')
        
        if schedule_divs:
            first_div = schedule_divs[0]
            h3_element = first_div.find('h3')
            session_name = h3_element.get_text().strip() if h3_element else "Unknown"
            
            print(f"Sample session: {session_name}")
            
            # Check for encoding issues in session name
            if 'â' in session_name or 'Ã' in session_name:
                print("❌ Encoding issues in session name")
            else:
                print("✅ Session name looks clean")
            
            # Find first paper
            paper_elements = first_div.find_all('strong')
            if paper_elements:
                first_paper = paper_elements[0]
                paper_text = first_paper.get_text().strip()
                print(f"Sample paper text: {paper_text}")
                
                if 'â' in paper_text or 'Ã' in paper_text:
                    print("❌ Encoding issues in paper text")
                else:
                    print("✅ Paper text looks clean")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
    
    print("\n=== ENCODING TEST COMPLETE ===")

if __name__ == "__main__":
    test_scraper_encoding()
