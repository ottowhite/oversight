import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from AuthorExtractor import AuthorInfo, extract_authors


class TestArxiv:
    """ArXiv papers: comma-separated author names in document.metadata.arXivRaw.authors."""

    def test_simple_list(self):
        doc = {"metadata": {"arXivRaw": {"authors": "Qing Jiao, Yushan Li, Jianping He"}}}
        result = extract_authors(doc, "arxiv")
        assert result.authors == ["Qing Jiao", "Yushan Li", "Jianping He"]
        assert result.institutions == []

    def test_with_and(self):
        doc = {
            "metadata": {
                "arXivRaw": {"authors": "Alice Smith, Bob Jones, and Carol White"}
            }
        }
        result = extract_authors(doc, "arxiv")
        assert result.authors == ["Alice Smith", "Bob Jones", "Carol White"]

    def test_single_author(self):
        doc = {"metadata": {"arXivRaw": {"authors": "John Doe"}}}
        result = extract_authors(doc, "arxiv")
        assert result.authors == ["John Doe"]

    def test_missing_authors_field(self):
        doc = {"metadata": {"arXivRaw": {}}}
        result = extract_authors(doc, "arxiv")
        assert result.authors == []


class TestOpenReview:
    """OpenReview (ICLR, NeurIPS, ICML): list of author name strings."""

    def test_iclr_v1(self):
        doc = {"content": {"authors": ["Casey Chu", "Kentaro Minami", "Kenji Fukumizu"]}}
        result = extract_authors(doc, "ICLR")
        assert result.authors == ["Casey Chu", "Kentaro Minami", "Kenji Fukumizu"]
        assert result.institutions == []

    def test_neurips(self):
        doc = {"content": {"authors": ["Janardhan Kulkarni", "Yin Tat Lee", "Daogao Liu"]}}
        result = extract_authors(doc, "NeurIPS")
        assert result.authors == ["Janardhan Kulkarni", "Yin Tat Lee", "Daogao Liu"]

    def test_icml_v2_format(self):
        doc = {"content": {"authors": {"value": ["Alice", "Bob"]}}}
        result = extract_authors(doc, "ICML")
        assert result.authors == ["Alice", "Bob"]

    def test_missing_content(self):
        doc = {}
        result = extract_authors(doc, "ICLR")
        assert result.authors == []


class TestVLDB:
    """VLDB: list of {"Name": str, "Affiliation": str} objects."""

    def test_basic(self):
        doc = {
            "authors": [
                {"Name": "Gengrui Zhang", "Affiliation": "University of Toronto"},
                {"Name": "Shiquan Zhang", "Affiliation": "University of Toronto"},
                {"Name": "Hans-Arno Jacobsen", "Affiliation": "University of Toronto"},
            ]
        }
        result = extract_authors(doc, "VLDB")
        assert result.authors == ["Gengrui Zhang", "Shiquan Zhang", "Hans-Arno Jacobsen"]
        # Deduped institutions
        assert result.institutions == ["University of Toronto"]

    def test_multiple_institutions(self):
        doc = {
            "authors": [
                {"Name": "Zengyang Gong", "Affiliation": "The Hong Kong University of Science and Technology"},
                {"Name": "yuxiang Zeng", "Affiliation": "Beihang University"},
                {"Name": "Lei Chen", "Affiliation": "The Hong Kong University of Science and Technology"},
            ]
        }
        result = extract_authors(doc, "VLDB")
        assert result.authors == ["Zengyang Gong", "yuxiang Zeng", "Lei Chen"]
        assert result.institutions == [
            "The Hong Kong University of Science and Technology",
            "Beihang University",
        ]


class TestMLSys:
    """MLSys: middle-dot-separated author names."""

    def test_basic(self):
        doc = {"authors": "Elias Frantar · Dan Alistarh"}
        result = extract_authors(doc, "MLSys")
        assert result.authors == ["Elias Frantar", "Dan Alistarh"]
        assert result.institutions == []

    def test_many_authors(self):
        doc = {"authors": "Ye Tian · Zhen Jia · Ziyue Luo · Yida Wang · Chuan Wu"}
        result = extract_authors(doc, "MLSys")
        assert result.authors == ["Ye Tian", "Zhen Jia", "Ziyue Luo", "Yida Wang", "Chuan Wu"]


class TestUsenix:
    """USENIX (OSDI, NSDI, ATC): semicolon-delimited 'Name(s),Affiliation' groups."""

    def test_osdi_single_author_per_group(self):
        doc = {
            "authors": "Yao Fu,University of Edinburgh;Dmitrii Ustiugov,NTU Singapore;Luo Mai,University of Edinburgh"
        }
        result = extract_authors(doc, "OSDI")
        assert result.authors == ["Yao Fu", "Dmitrii Ustiugov", "Luo Mai"]
        assert result.institutions == [
            "University of Edinburgh",
            "NTU Singapore",
        ]

    def test_nsdi_multi_author_with_and(self):
        doc = {
            "authors": "Chenyuan Wu and Haoyun Qin,University of Pennsylvania;Mohammad Javad Amiri,Stony Brook University;Boon Thau Loo,University of Pennsylvania"
        }
        result = extract_authors(doc, "NSDI")
        assert result.authors == [
            "Chenyuan Wu",
            "Haoyun Qin",
            "Mohammad Javad Amiri",
            "Boon Thau Loo",
        ]
        assert "University of Pennsylvania" in result.institutions
        assert "Stony Brook University" in result.institutions

    def test_atc_complex(self):
        doc = {
            "authors": "Rachee Singh, Sharad Agarwal, Matt Calder, and Paramvir Bahl,Microsoft"
        }
        result = extract_authors(doc, "NSDI")
        assert result.authors == [
            "Rachee Singh",
            "Sharad Agarwal",
            "Matt Calder",
            "Paramvir Bahl",
        ]
        assert result.institutions == ["Microsoft"]

    def test_osdi_full_paper(self):
        doc = {
            "authors": "Nikita Lazarev and Varun Gohil,MIT, CSAIL;James Tsai, Andy Anderson, and Bhushan Chitlur,Intel Labs;Zhiru Zhang,Cornell University;Christina Delimitrou,MIT, CSAIL"
        }
        result = extract_authors(doc, "OSDI")
        assert result.authors == [
            "Nikita Lazarev",
            "Varun Gohil",
            "James Tsai",
            "Andy Anderson",
            "Bhushan Chitlur",
            "Zhiru Zhang",
            "Christina Delimitrou",
        ]
        assert "MIT, CSAIL" in result.institutions
        assert "Intel Labs" in result.institutions
        assert "Cornell University" in result.institutions

    def test_nsdi_long_affiliation(self):
        doc = {
            "authors": "Ruili Liu,Tsinghua University and University of Electronic Science and Technology of China;Teng Ma,Alibaba Group"
        }
        result = extract_authors(doc, "NSDI")
        assert result.authors == ["Ruili Liu", "Teng Ma"]
        assert result.institutions == [
            "Tsinghua University and University of Electronic Science and Technology of China",
            "Alibaba Group",
        ]


class TestParenthetical:
    """Parenthetical format (SOSP, ASPLOS, EuroSys): 'Name (Affiliation), ...'"""

    def test_sosp(self):
        doc = {
            "authors": "Kostis Kaffes (Stanford University), Jack Tigar Humphries (Stanford University), David Mazières (Stanford University), Christos Kozyrakis (Stanford University)"
        }
        result = extract_authors(doc, "SOSP")
        assert result.authors == [
            "Kostis Kaffes",
            "Jack Tigar Humphries",
            "David Mazières",
            "Christos Kozyrakis",
        ]
        assert result.institutions == ["Stanford University"]

    def test_asplos(self):
        doc = {
            "authors": "Harsh Desai (Carnegie Mellon University), Xinye Wang (Carnegie Mellon University), Brandon Lucia (Carnegie Mellon University)"
        }
        result = extract_authors(doc, "ASPLOS")
        assert result.authors == ["Harsh Desai", "Xinye Wang", "Brandon Lucia"]
        assert result.institutions == ["Carnegie Mellon University"]

    def test_eurosys_mixed_affiliations(self):
        doc = {
            "authors": "Ziming Mao (UC Berkeley), Tian Xia (UC Berkeley), Romil Bhardwaj (UC Berkeley), Zongheng Yang (UC Berkeley), Scott Shenker (ICSI AND UC Berkeley), Ion Stoica (UC Berkeley)"
        }
        result = extract_authors(doc, "EuroSys")
        assert "Ziming Mao" in result.authors
        assert "Scott Shenker" in result.authors
        assert "UC Berkeley" in result.institutions
        assert "ICSI AND UC Berkeley" in result.institutions

    def test_sosp_nested_parens_in_affiliation(self):
        doc = {
            "authors": "Hao Sun (School of Software, Tsinghua University, KLISS, BNRist, China), Ting Chen (Center for Cybersecurity, University of Electronic Science and Technology of China, China)"
        }
        result = extract_authors(doc, "SOSP")
        assert result.authors == ["Hao Sun", "Ting Chen"]
        assert len(result.institutions) == 2


class TestEdgeCases:
    """Edge cases and fallback behavior."""

    def test_unknown_source_with_parenthetical(self):
        doc = {"authors": "Alice (MIT), Bob (Stanford)"}
        result = extract_authors(doc, "SomeNewConf")
        assert result.authors == ["Alice", "Bob"]
        assert result.institutions == ["MIT", "Stanford"]

    def test_unknown_source_with_semicolon(self):
        doc = {"authors": "Alice and Bob,MIT;Carol,Stanford"}
        result = extract_authors(doc, "SomeNewConf")
        assert result.authors == ["Alice", "Bob", "Carol"]

    def test_none_source(self):
        doc = {"authors": "Alice, Bob, Carol"}
        result = extract_authors(doc, None)
        assert result.authors == ["Alice", "Bob", "Carol"]

    def test_no_authors_field(self):
        doc = {"title": "Some Paper"}
        result = extract_authors(doc, "OSDI")
        assert result.authors == []
        assert result.institutions == []

    def test_empty_string(self):
        doc = {"authors": ""}
        result = extract_authors(doc, "MLSys")
        assert result.authors == []
