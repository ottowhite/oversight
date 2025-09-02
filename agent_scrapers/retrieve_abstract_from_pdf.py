import os
import hashlib
import pickle
import requests
from pathlib import Path
from docling.document_converter import DocumentConverter
import re


def get_cache_dir():
    """Create and return the cache directory path."""
    cache_dir = Path(__file__).parent / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


def get_file_hash(url):
    """Generate a hash for the URL to use as filename."""
    return hashlib.md5(url.encode()).hexdigest()


def download_pdf_with_cache(url):
    """Download PDF from URL with caching."""
    cache_dir = get_cache_dir()
    file_hash = get_file_hash(url)
    pdf_path = cache_dir / f"{file_hash}.pdf"
    
    # Check if PDF is already cached
    if pdf_path.exists():
        print(f"PDF found in cache: {pdf_path}")
        return pdf_path
    
    # Download PDF
    print(f"Downloading PDF from: {url}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(pdf_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"PDF downloaded and cached: {pdf_path}")
        return pdf_path
        
    except requests.RequestException as e:
        print(f"Error downloading PDF: {e}")
        return None


def parse_pdf_with_cache(pdf_path):
    """Parse PDF using docling with caching."""
    cache_dir = get_cache_dir()
    parsed_cache_path = cache_dir / f"{pdf_path.stem}_parsed.txt"
    
    # Check if parsed content is already cached
    if parsed_cache_path.exists():
        print(f"Parsed content found in cache: {parsed_cache_path}")
        with open(parsed_cache_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    # Parse PDF with docling
    print(f"Parsing PDF with docling: {pdf_path}")
    try:
        converter = DocumentConverter()
        result = converter.convert(pdf_path)
        
        # Extract text content from the result
        content = result.document.export_to_markdown()
        
        # Cache the parsed content as text
        with open(parsed_cache_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"PDF parsed and cached: {parsed_cache_path}")
        return content
        
    except Exception as e:
        print(f"Error parsing PDF: {e}")
        return None


def extract_abstract(content):
    """Extract abstract from parsed document content."""
    if not content:
        return None
    
    # Try multiple patterns to find the abstract
    abstract_patterns = [
        r'(?i)^#*\s*abstract\s*$.*?(?=^#|\Z)',  # Abstract section
        r'(?i)abstract\s*[:\-]?\s*(.*?)(?=\n\s*(?:keywords?|introduction|1\.|background)|$)',  # Abstract paragraph
        r'(?i)abstract\s*\n\s*(.*?)(?=\n\s*\n|\n\s*[A-Z]|\Z)',  # Abstract with newline
    ]
    
    for pattern in abstract_patterns:
        matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL)
        if matches:
            abstract = matches[0].strip()
            # Clean up the abstract
            abstract = re.sub(r'\n+', ' ', abstract)  # Replace multiple newlines with space
            abstract = re.sub(r'\s+', ' ', abstract)  # Replace multiple spaces with single space
            # Remove title markers like "## ABSTRACT" or "ABSTRACT" from the beginning
            abstract = re.sub(r'^#+\s*abstract\s*', '', abstract, flags=re.IGNORECASE).strip()
            abstract = re.sub(r'^abstract\s*:?\s*', '', abstract, flags=re.IGNORECASE).strip()
            abstract = abstract.strip()
            if len(abstract) > 50:  # Ensure it's a substantial abstract
                return abstract
    
    # If no structured abstract found, try to find abstract-like content
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(?i)abstract', line):
            # Look for content in next few lines
            abstract_content = []
            for j in range(i + 1, min(i + 10, len(lines))):
                if lines[j].strip() and not re.match(r'^#|^keywords?|^introduction|^1\.', lines[j], re.I):
                    abstract_content.append(lines[j].strip())
                elif abstract_content:
                    break
            
            if abstract_content:
                abstract = ' '.join(abstract_content)
                abstract = re.sub(r'\s+', ' ', abstract)
                # Remove title markers like "## ABSTRACT" or "ABSTRACT" from the beginning
                abstract = re.sub(r'^#+\s*abstract\s*', '', abstract, flags=re.IGNORECASE).strip()
                abstract = re.sub(r'^abstract\s*:?\s*', '', abstract, flags=re.IGNORECASE).strip()
                if len(abstract) > 50:
                    return abstract
    
    return "Abstract not found in document"


def main():
    """Main function to download, parse, and extract abstract."""
    paper_pdf_url = "https://www.vldb.org/2025/Workshops/VLDB-Workshops-2025/DEC/DEC25_5.pdf"
    
    # Download PDF with caching
    pdf_path = download_pdf_with_cache(paper_pdf_url)
    if not pdf_path:
        print("Failed to download PDF")
        return
    
    # Parse PDF with caching
    parsed_content = parse_pdf_with_cache(pdf_path)
    if not parsed_content:
        print("Failed to parse PDF")
        return
    
    # Extract abstract
    abstract = extract_abstract(parsed_content)
    print(abstract)


if __name__ == "__main__":
    main()
