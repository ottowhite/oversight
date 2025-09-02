#!/usr/bin/env python3
"""
Diagnostic script to identify where encoding issues are introduced in the web scraping pipeline.
"""

import requests
from cached_webpage_retriever import get_cached_webpage
from bs4 import BeautifulSoup
import chardet

def diagnose_encoding_pipeline():
    """Test encoding at different stages of the pipeline."""
    # Test URL - let's use the main VLDB schedule page
    test_url = "https://vldb.org/2025/?program-schedule-2025"
    
    print("=== ENCODING PIPELINE DIAGNOSIS ===\n")
    
    # Stage 1: Raw requests response
    print("Stage 1: Raw requests.get() response")
    print("-" * 40)
    
    try:
        response = requests.get(test_url, headers={
            'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        })
        
        print(f"Response status: {response.status_code}")
        print(f"Response encoding (requests detected): {response.encoding}")
        print(f"Response headers Content-Type: {response.headers.get('Content-Type', 'Not specified')}")
        
        # Check raw bytes encoding
        raw_bytes = response.content[:2000]  # First 2KB
        detected_encoding = chardet.detect(raw_bytes)
        print(f"Detected encoding from raw bytes: {detected_encoding}")
        
        # Get text using different methods
        text_auto = response.text[:1000]
        text_utf8 = response.content.decode('utf-8', errors='ignore')[:1000]
        text_latin1 = response.content.decode('latin-1', errors='ignore')[:1000]
        
        print(f"\nSample text (auto): {repr(text_auto[:200])}")
        print(f"Sample text (UTF-8): {repr(text_utf8[:200])}")
        print(f"Sample text (Latin-1): {repr(text_latin1[:200])}")
        
    except Exception as e:
        print(f"Error in Stage 1: {e}")
    
    print("\n" + "="*60 + "\n")
    
    # Stage 2: Cached webpage retriever
    print("Stage 2: get_cached_webpage() result")
    print("-" * 40)
    
    try:
        cached_content = get_cached_webpage(test_url)
        print(f"Content length: {len(cached_content)}")
        print(f"Sample content: {repr(cached_content[:500])}")
        
        # Look for specific problematic characters
        if 'â' in cached_content:
            print("❌ Found problematic 'â' character in cached content")
        if 'Ã' in cached_content:
            print("❌ Found problematic 'Ã' character in cached content")
        if "'" in cached_content:
            print("✅ Found correct right single quote character")
        if '×' in cached_content:
            print("✅ Found correct multiplication sign")
            
    except Exception as e:
        print(f"Error in Stage 2: {e}")
    
    print("\n" + "="*60 + "\n")
    
    # Stage 3: BeautifulSoup parsing
    print("Stage 3: BeautifulSoup parsing")
    print("-" * 40)
    
    try:
        # Test different BeautifulSoup parsers
        parsers = ['html.parser', 'lxml', 'html5lib']
        
        for parser in parsers:
            try:
                print(f"\nTesting with {parser} parser:")
                soup = BeautifulSoup(cached_content, parser)
                
                # Extract some text that might contain special characters
                sample_elements = soup.find_all(['h1', 'h2', 'h3', 'p', 'strong'])[:10]
                for elem in sample_elements:
                    text = elem.get_text()
                    if any(char in text for char in ['â', 'Ã', "'", '×']):
                        print(f"  Found special chars in: {repr(text[:100])}")
                        
            except Exception as e:
                print(f"  Error with {parser}: {e}")
                
    except Exception as e:
        print(f"Error in Stage 3: {e}")
    
    print("\n" + "="*60 + "\n")
    
    # Stage 4: Test specific paper page
    print("Stage 4: Testing specific paper page with known issues")
    print("-" * 40)
    
    # Use the Vortex paper URL that we know has issues
    paper_url = "https://vldb.org/pvldb/volumes/18/paper/Vortex%3A%20Overcoming%20Memory%20Capacity%20Limitations%20in%20GPU-Accelerated%20Large-Scale%20Data%20Analytics"
    
    try:
        paper_content = get_cached_webpage(paper_url)
        soup = BeautifulSoup(paper_content, 'html.parser')
        
        # Look for the abstract
        abstract_elements = [
            soup.find('div', {'class': 'abstract'}),
            soup.find('section', {'class': 'abstract'}),
            soup.find('p', {'class': 'abstract'}),
            soup.find('div', {'id': 'abstract'}),
        ]
        
        abstract_text = ""
        for elem in abstract_elements:
            if elem:
                abstract_text = elem.get_text().strip()
                break
        
        if not abstract_text:
            # Look for text patterns
            all_elements = soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'div'])
            for i, element in enumerate(all_elements):
                if element.get_text().strip().lower() in ['abstract', 'abstract:', 'abstract.']:
                    if i + 1 < len(all_elements):
                        abstract_text = all_elements[i + 1].get_text().strip()
                        break
        
        print(f"Abstract found: {bool(abstract_text)}")
        if abstract_text:
            print(f"Abstract sample: {repr(abstract_text[:300])}")
            
            # Check for specific encoding issues
            if 'GPUâs' in abstract_text:
                print("❌ Found 'GPUâs' - encoding issue present")
            if "GPU's" in abstract_text:
                print("✅ Found correct 'GPU's'")
            if '5.7 Ã' in abstract_text:
                print("❌ Found '5.7 Ã' - encoding issue present")
            if '5.7 ×' in abstract_text:
                print("✅ Found correct '5.7 ×'")
                
    except Exception as e:
        print(f"Error in Stage 4: {e}")

def test_encoding_fixes():
    """Test different approaches to fix encoding at the source."""
    print("\n" + "="*60)
    print("TESTING SOURCE-LEVEL ENCODING FIXES")
    print("="*60 + "\n")
    
    test_url = "https://vldb.org/2025/?program-schedule-2025"
    
    # Method 1: Force UTF-8 encoding in requests
    print("Method 1: Force UTF-8 encoding in requests")
    print("-" * 45)
    
    try:
        response = requests.get(test_url, headers={
            'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        })
        
        # Force UTF-8 encoding
        response.encoding = 'utf-8'
        forced_utf8_text = response.text
        
        print(f"Sample with forced UTF-8: {repr(forced_utf8_text[:300])}")
        
    except Exception as e:
        print(f"Error in Method 1: {e}")
    
    print("\n" + "-"*60 + "\n")
    
    # Method 2: Use raw bytes and explicitly decode
    print("Method 2: Explicit UTF-8 decode from bytes")
    print("-" * 45)
    
    try:
        response = requests.get(test_url, headers={
            'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        })
        
        explicit_utf8_text = response.content.decode('utf-8', errors='replace')
        
        print(f"Sample with explicit decode: {repr(explicit_utf8_text[:300])}")
        
    except Exception as e:
        print(f"Error in Method 2: {e}")
    
    print("\n" + "-"*60 + "\n")
    
    # Method 3: Test BeautifulSoup with from_encoding parameter
    print("Method 3: BeautifulSoup with explicit encoding")
    print("-" * 45)
    
    try:
        response = requests.get(test_url, headers={
            'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        })
        
        # Parse with explicit encoding
        soup_utf8 = BeautifulSoup(response.content, 'html.parser', from_encoding='utf-8')
        sample_text = soup_utf8.get_text()[:300]
        
        print(f"Sample with BeautifulSoup UTF-8: {repr(sample_text)}")
        
    except Exception as e:
        print(f"Error in Method 3: {e}")

if __name__ == "__main__":
    diagnose_encoding_pipeline()
    test_encoding_fixes()
