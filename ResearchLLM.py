from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
import relevant_abstracts

class ResearchLLM:
    def __init__(self, model_name: str):
        load_dotenv()

        assert os.environ["OPENROUTER_API_KEY"] is not None, "OPENROUTER_API_KEY is not set"
        self.llm = ChatOpenAI(
            model=model_name,
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"]
        )

        importance_rankings_dict = {
            "Focus on optimising agentic applications/LLM applications rather than single LLM inference": 20,
            "Making improvements to specifically to LLM Scheduling, primarily for agentic applications": 10,
            "Supports dynamic LLM applications with control flow (loops/conditionals), could be implied by mentioning inference-time scaling/LLM searches/self-refinement for half points": 10,
            "Efficient sharing of hardware between multiple locally hosted LLMs, must be about multiple LLMs but could be outside the context of agentic applications": 10,
            "Supporting a combination of local and remote LLMs, could be outside the context of agentic applications": 10
        }
        self.importance_rankings_total_score = sum(importance_rankings_dict.values())
        self.importance_rankings_string = "\n".join([f"{i+1}. {k} [{v} points]" for i, (k, v) in enumerate(importance_rankings_dict.items())])

        self.project_context = "How to improve efficiency of LLM-Applications / agentic workflows, as traditional LLM frameworks only optimise for individual invocations, whereas more complex LLM-applications such as RAG, tool-use, and inference-time scaling are becoming commonplace. We are particularly looking at scheduling improvements that can be made with a graph representing such high-level LLM-Applications. Interesting future directions include how to predict the future execution latency of the graph, better support for dynamic control flow such as loops and conditionals, how to share hardware efficiently between a combination of locally hosted models, and remote models."
        self.not_project_context = "LLM Training, Quantisation, Compression, optimisation of individual LLM inference"

    def generate_relatedness_summary(self, abstract: str):
        prompt = f"""You are an academic research assistant that concisely and accurately determines relatedness of a research abstract to our given project context. 

        Our project context is:
        \"{self.project_context}\"

        Our project is not related to:
        \"{self.not_project_context}\"

        The importance rankings of the different aspects of the abstract are:
        \"{self.importance_rankings_string}\"

        The abstract of the paper is:
        \"{abstract}\"

        Generate a 80 word summary about the how the different aspects of this abstract could relate to the project context. Finish your answer by scoring the abstract on the importance rankings with individual X/Y scores on new lines with few word but specific to LLM application category names (and single-sentence justification on newline and indented), and generating a final score out of {self.importance_rankings_total_score} with a percentage. Add newlines between each category and justification.
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
    print(research_llm.generate_relatedness_summary(relevant_abstracts.tempo_abstract))