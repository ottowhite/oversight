from typing import Set
import pytest
from vldb_scraper import extract_papers, Paper, Author, vldb_schedule_link


class TestVLDBScraper:
    """Test class for VLDB scraper functionality."""
    
    def test_extract_papers_contains_different_paper(self) -> None:
        """Test that extract_papers function extracts papers and different_paper is a member."""
        print("\n=== Testing extract_papers_contains_different_paper ===")

        example_paper: Paper = Paper(
            title="Ursa: A Lakehouse-Native Data Streaming Engine for Kafka",
            abstract="Data lakehouse architectures unify the cost-efficiency of data lakes with the transactional guarantees of data warehouses. Yet, real-time ingestion often depends on external streaming systems such as Apache Kafka, along with bespoke connectors that read from Kafka and write into the lakehouse—leading to increased complexity and high operational costs. In particular, traditional leader-based data streaming platforms are designed for sub-100 ms low-latency workloads; however, when used for data-intensive ingestion in a cloud environment, cross availability-zone (AZ) disk-based replication significantly raises total infrastructure costs due to excessive network traffic and overprovisioned disk storage. This paper introduces Ursa, a leaderless, cloud-native, and Kafka-compatible streaming engine that writes data directly to open lakehouse tables on object storage. By eliminating leader-based replication, disk-based broker storage, and external connectors, Ursa markedly reduces infrastructure costs while preserving high throughput, exactly-once semantics, and near-real-time streaming capabilities. Experimental results show that Ursa matches the performance of traditional Kafka clusters at a fraction of the cost, offering up to a 10x reduction in infrastructure expenses.",
            conference_link="https://vldb.org/pvldb/volumes/18/paper/Ursa%3A%20A%20Lakehouse-Native%20Data%20Streaming%20Engine%20for%20Kafka",
            pdf_link="https://www.vldb.org/pvldb/vol18/p5184-guo.pdf",
            session="Industry 1: Distributed Systems",
            authors=(
                Author(name="Sijie Guo", affiliation="StreamNative"),
                Author(name="Matteo Merli", affiliation="StreamNative"),
                Author(name="Hang Chen", affiliation="StreamNative"),
                Author(name="Neng Lu", affiliation="StreamNative"),
                Author(name="Penghui Li", affiliation="StreamNative")
            ),
            date="2025-09-01",
            conference="VLDB"
        )

        print(f"Looking for paper: {example_paper.title}")
        print(f"Expected session: {example_paper.session}")
        print(f"Expected conference_link: {example_paper.conference_link}")
        print(f"Expected pdf_link: {example_paper.pdf_link}")
        print(f"Expected authors: {len(example_paper.authors)} authors")
        
        print("\nExtracting papers from schedule...")
        extracted_papers: Set[Paper] = extract_papers(vldb_schedule_link)
        
        print(f"\nExtracted {len(extracted_papers)} papers total")
        
        # Show some extracted papers for debugging
        print("\nFirst 5 extracted papers:")
        for i, paper in enumerate(list(extracted_papers)[:5]):
            print(f"{i+1}. Title: {paper.title}")
            print(f"   Session: {paper.session}")
            print(f"   Conference Link: {paper.conference_link}")
            print(f"   PDF Link: {paper.pdf_link}")
            print(f"   Authors: {len(paper.authors)} authors")
            print(f"   Abstract length: {len(paper.abstract)} chars")
            print()
        
        # Check if our target paper is in the set
        found_paper = None
        for paper in extracted_papers:
            if paper.title == example_paper.title:
                found_paper = paper
                break
        
        if found_paper:
            print(f"✓ Found target paper: {found_paper.title}")
            print(f"  Session matches: {found_paper.session == example_paper.session}")
            print(f"  Conference link matches: {found_paper.conference_link == example_paper.conference_link}")
            print(f"  PDF link matches: {found_paper.pdf_link == example_paper.pdf_link}")
            print(f"  Authors count matches: {len(found_paper.authors) == len(example_paper.authors)}")
            print(f"  Abstract length: {len(found_paper.abstract)}")
        else:
            print("✗ Target paper not found in extracted papers")
            # Show titles that might be similar
            print("Papers with 'Ursa' in title:")
            for paper in extracted_papers:
                if 'Ursa' in paper.title:
                    print(f"  - {paper.title}")
        
        assert example_paper in extracted_papers, "different_paper should be in the extracted papers set"
    
    def test_subset_of_sessions_present(self) -> None:
        print("\n=== Testing subset_of_sessions_present ===")
        
        sessions_sublist = [
            "Panel 1: Neural Relational Data: Tabular Foundation Models, LLMs... or both?",
            "Tutorial 1: Property Graph Standards: State of the Art & Open Challenges",
            "Industry 1: Distributed Systems",
            "Research 1: Cloud Data Management",
            "Research 2: Applied ML and AI for Data Management I",
            "Research 26: Distributed Transactions I",
            "Research 40: Time Series and Vector Data",
            "Demo C2:"
        ]

        print(f"Expected sessions to find ({len(sessions_sublist)}):")
        for session in sessions_sublist:
            print(f"  - {session}")

        print("\nExtracting papers from schedule...")
        extracted_papers: Set[Paper] = extract_papers(vldb_schedule_link)
        
        # Extract unique session names from the papers
        extracted_sessions: Set[str] = {paper.session for paper in extracted_papers}
        
        print(f"\nFound {len(extracted_sessions)} unique sessions:")
        for session in sorted(extracted_sessions):
            print(f"  - {session}")
        
        print(f"\nChecking if expected sessions are present:")
        
        # Assert that each session in the subset is present in the extracted sessions
        for session in sessions_sublist:
            is_present = session in extracted_sessions
            status = "✓" if is_present else "✗"
            print(f"  {status} {session}")
            if not is_present:
                # Look for similar sessions
                similar_sessions = [s for s in extracted_sessions if any(word in s for word in session.split()[:3])]
                if similar_sessions:
                    print(f"    Similar sessions found: {similar_sessions}")
            assert session in extracted_sessions, f"Session '{session}' should be present in extracted sessions"


if __name__ == "__main__":
    pytest.main([__file__])