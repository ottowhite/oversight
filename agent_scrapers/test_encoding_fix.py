#!/usr/bin/env python3
"""
Test script to verify that the encoding fix in cached_webpage_retriever works correctly.
"""

from cached_webpage_retriever import get_cached_webpage
from bs4 import BeautifulSoup

def test_encoding_fix():
    """Test that the encoding fix properly handles UTF-8 characters."""
    print("=== TESTING ENCODING FIX ===\n")
    
    # Test the main VLDB schedule page
    test_url = "https://vldb.org/2025/?program-schedule-2025"
    
    print("Fetching VLDB schedule page with encoding fix...")
    content = get_cached_webpage(test_url)
    
    # Check for problematic characters that indicate encoding issues
    has_encoding_issues = False
    
    if 'â' in content:
        print("❌ Still found problematic 'â' character")
        has_encoding_issues = True
    else:
        print("✅ No problematic 'â' character found")
    
    if 'Ã' in content and 'Ã' not in content:  # Ã without proper accents indicates issues
        print("❌ Still found problematic 'Ã' character (not proper accents)")
        has_encoding_issues = True
    else:
        print("✅ No problematic 'Ã' character found")
    
    # Check for correct UTF-8 characters
    if "'" in content or "'" in content:
        print("✅ Found correct UTF-8 quotation marks")
    
    if '×' in content:
        print("✅ Found correct UTF-8 multiplication sign")
    
    print(f"\nOverall encoding status: {'❌ ISSUES REMAIN' if has_encoding_issues else '✅ LOOKS GOOD'}")
    
    # Test a specific paper page that we know had issues
    print("\n" + "-"*60)
    print("Testing specific paper page (Vortex paper)...")
    
    paper_url = "https://vldb.org/pvldb/volumes/18/paper/Vortex%3A%20Overcoming%20Memory%20Capacity%20Limitations%20in%20GPU-Accelerated%20Large-Scale%20Data%20Analytics"
    
    try:
        paper_content = get_cached_webpage(paper_url)
        soup = BeautifulSoup(paper_content, 'html.parser')
        
        # Extract abstract
        abstract_text = ""
        abstract_patterns = [
            soup.find('div', {'class': 'abstract'}),
            soup.find('section', {'class': 'abstract'}),
            soup.find('p', {'class': 'abstract'}),
            soup.find('div', {'id': 'abstract'}),
        ]
        
        for pattern in abstract_patterns:
            if pattern:
                abstract_text = pattern.get_text().strip()
                break
        
        if not abstract_text:
            # Look for text patterns
            all_elements = soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'div'])
            for i, element in enumerate(all_elements):
                if element.get_text().strip().lower() in ['abstract', 'abstract:', 'abstract.']:
                    if i + 1 < len(all_elements):
                        abstract_text = all_elements[i + 1].get_text().strip()
                        break
        
        if abstract_text:
            print(f"Abstract found: {len(abstract_text)} characters")
            
            # Check specific known problematic patterns
            if 'GPUâs' in abstract_text:
                print("❌ Still found 'GPUâs' - encoding issue remains")
            elif "GPU's" in abstract_text or "GPUs'" in abstract_text:
                print("✅ Found correct GPU apostrophe")
            else:
                print("? No GPU apostrophe found to test")
            
            if '5.7 Ã' in abstract_text:
                print("❌ Still found '5.7 Ã' - encoding issue remains")
            elif '5.7 ×' in abstract_text:
                print("✅ Found correct '5.7 ×'")
            else:
                print("? No multiplication sign found to test")
            
            # Show a sample of the abstract
            print(f"\nAbstract sample (first 200 chars):")
            print(repr(abstract_text[:200]))
            
        else:
            print("❌ Could not extract abstract for testing")
    
    except Exception as e:
        print(f"❌ Error testing paper page: {e}")
    
    print("\n=== ENCODING TEST COMPLETE ===")

if __name__ == "__main__":
    test_encoding_fix()
