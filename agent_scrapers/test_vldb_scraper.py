from typing import Set
import pytest
from vldb_scraper import extract_papers, Paper, Author, vldb_schedule_link


class TestVLDBScraper:
    """Test class for VLDB scraper functionality."""
    
    def test_extract_papers_contains_different_paper(self) -> None:
        """Test that extract_papers function extracts papers and different_paper is a member."""

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


        extracted_papers, skipped_papers = extract_papers(vldb_schedule_link)

        
        # Check if our target paper is in the set
        found_paper = None
        for paper in extracted_papers:
            if paper.title == example_paper.title:
                found_paper = paper
                break
        

        
        assert example_paper in extracted_papers, "different_paper should be in the extracted papers set"
    
    def test_subset_of_sessions_present(self) -> None:
        
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


        extracted_papers, skipped_papers = extract_papers(vldb_schedule_link)
        
        # Extract unique session names from the papers
        extracted_sessions: Set[str] = {paper.session for paper in extracted_papers}
        
        # Assert that each session in the subset is present in the extracted sessions
        for session in sessions_sublist:
            assert session in extracted_sessions, f"Session '{session}' should be present in extracted sessions"
    
    def test_unlinked_papers_not_in_result(self):
        """
        Test that papers known to be unlinked (e.g., missing conference_link or pdf_link)
        are present in the skipped papers set and not in the extracted papers set.
        """
        unlinked_titles = [
            "Locator: Local Stability for Rankings",
            "OmniTune: A universal framework for query refinement via LLMs",
            "Sentence to Model: Cost‑Effective Data Collection LLM Agent",
            "SWOOP: Top-k Similarity Joins over Set Streams",
            "SHARQ: Explainability Framework for Association Rules on Relational Data",
            "A Survey of Multimodal Event Detection Based on Data Fusion",
            "Grouping, subsumption, and disjunctive join optimisations in Oracle",
            "Model Reusability in Reinforcement Learning",
            "GRELA: Exploiting Graph Representation Learning in Effective Approximate Query Processing",
            "In-Database Query Optimization on SQL with ML Predicates",
            "SunStorm: Geographically distributed transactions over Aurora-style systems",
            "Join Optimization Revisited: A Novel DP Algorithm for Join & Sort Order Selection",
            "How Good Are Multi-dimensional Learned Indices? An Experimental Survey",
            "Languages and Systems for RDF Stream Processing, a Survey",
            "LIST: Learning to Index Spatio-Textual Data for Embedding based Spatial Keyword Queries",
            "Optimizing Navigational Graph Queries",
            "MINE GRAPH RULE: A New GQL Operator for Mining Association Rules in Property Graph Databases",
            "Survey of Vector Database Management Systems",
            "OLTP in the Cloud: Architectures, Tradeoffs, and Cost"
        ]



        # Extract papers from the schedule
        extracted_papers, skipped_papers = extract_papers(vldb_schedule_link)
        extracted_titles = {paper.title for paper in extracted_papers}
        skipped_titles = {skipped.paper.title for skipped in skipped_papers}



        # Check that none of the unlinked paper titles are in extracted papers
        unlinked_in_extracted = []
        for title in unlinked_titles:
            if title in extracted_titles:
                unlinked_in_extracted.append(title)

        if unlinked_in_extracted:
            assert False, f"Unlinked papers should not be in extracted results: {unlinked_in_extracted}"

        # Check that all unlinked titles are in skipped papers (check element text since titles may be empty)
        unlinked_in_skipped = []
        unlinked_not_found = []
        skipped_element_texts = [skipped.element_text for skipped in skipped_papers]
        
        for title in unlinked_titles:
            found = False
            # Check if title is in the skipped papers' titles
            if title in skipped_titles:
                found = True
            else:
                # Check if title is in the element text of any skipped paper
                for element_text in skipped_element_texts:
                    if title in element_text:
                        found = True
                        break
            
            if found:
                unlinked_in_skipped.append(title)
            else:
                unlinked_not_found.append(title)



        # Check for papers that were skipped but shouldn't have been
        unexpected_skipped = []
        for skipped in skipped_papers:
            if skipped.paper.title and skipped.paper.title not in unlinked_titles:
                unexpected_skipped.append(skipped)

        if unexpected_skipped:
            assert False, f"Unexpected papers were skipped: {[s.paper.title for s in unexpected_skipped]}"


if __name__ == "__main__":
    pytest.main([__file__])