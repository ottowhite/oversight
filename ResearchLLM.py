from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os

class ResearchLLM:
    def __init__(self, model_name: str):
        load_dotenv()

        assert os.environ["OPENROUTER_API_KEY"] is not None, "OPENROUTER_API_KEY is not set"
        self.llm = ChatOpenAI(
            model=model_name,
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"]
        )

        self.project_context = "How to improve efficiency of LLM-Applications / agentic workflows, as traditional LLM frameworks only optimise for individual invocations, whereas more complex LLM-applications such as RAG, tool-use, and inference-time scaling are becoming commonplace. We are particularly looking at scheduling improvements that can be made with a graph representing such high-level LLM-Applications. Interesting future directions include how to predict the future execution latency of the graph, better support for dynamic control flow such as loops and conditionals, how to share hardware efficiently between a combination of locally hosted models, and remote models."

        self.not_project_context = "LLM Training, Quantisation, Compression, optimisation of individual LLM inference"

    def generate_relatedness_summary(self, abstract: str):
        prompt = f"""You are an academic research assistant that concisely and accurately determines relatedness of a research abstract to our given project context. 

        Our project context is:
        \"{self.project_context}\"

        Our project is not related to:
        \"{self.not_project_context}\"

        The abstract of the paper is:
        \"{abstract}\"

        Generate a 80 word summary about the how the different aspects of this abstract could relate to the project context. Finish your answer with a score between 0 and 100, where 100 is the most related.
        """

        return self.llm.invoke(prompt).content
    
    def generate_fake_abstract(self, input_string: str, conference_type, output_type):
        assert output_type in ["Paper", "Survey"]

        if conference_type == "Systems":
            abstract_style = "conferences like OSDI, SOSP, ASPLOS"
        elif conference_type == "AI":
            abstract_style = "conferences like ICLR, ICML, NeurIPS"
        
        necessary_inclusions = """
        - key contributions
        - realistic results (if not a survey)
        - background
        - key related technologies used or examined
        """
        prompt = f"""You are an academic research assistant that generates a fake but realistic abstract for a research paper in the style of {abstract_style}.
        You must include at least these aspects to the abstract:
        {necessary_inclusions}
        Make an 100 word abstract of the following type: {output_type}

        The input string to generate the abstract from is:
        \"{input_string}\"

        Output only the abstract and no comments. Don't make up any information outside the scope of the provided text.
        """

        return self.llm.invoke(prompt).content


if __name__ == "__main__":
    research_llm = ResearchLLM(model_name="google/gemini-2.5-flash")

    sample_abstract = "Large Language Models (LLMs) have enabled remarkable progress in natural language processing, yet their high computational and memory demands pose challenges for deployment in resource-constrained environments. Although recent low-rank decomposition methods offer a promising path for structural compression, they often suffer from accuracy degradation, expensive calibration procedures, and result in inefficient model architectures that hinder real-world inference speedups. In this paper, we propose FLAT-LLM, a fast and accurate, training-free structural compression method based on fine-grained low-rank transformations in the activation space. Specifically, we reduce the hidden dimension by transforming the weights using truncated eigenvectors computed via head-wise Principal Component Analysis, and employ a greedy budget redistribution strategy to adaptively allocate ranks across decoders. FLAT-LLM achieves efficient and effective weight compression without recovery fine-tuning, which could complete the calibration within a few minutes. Evaluated across 5 models and 11 datasets, FLAT-LLM outperforms structural pruning baselines in generalization and downstream performance, while delivering inference speedups over decomposition-based methods."

    print(research_llm.generate_relatedness_summary(sample_abstract))