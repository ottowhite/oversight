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
                Author(Name="Sijie Guo", Affiliation="StreamNative"),
                Author(Name="Matteo Merli", Affiliation="StreamNative"),
                Author(Name="Hang Chen", Affiliation="StreamNative"),
                Author(Name="Neng Lu", Affiliation="StreamNative"),
                Author(Name="Penghui Li", Affiliation="StreamNative")
            ),
            date="2025-09-01",
            conference="VLDB"
        )

        extracted_papers: Set[Paper] = extract_papers(vldb_schedule_link)
        assert example_paper in extracted_papers, "different_paper should be in the extracted papers set"

if __name__ == "__main__":
    pytest.main([__file__])