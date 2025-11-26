from relevant_abstracts import autellix_abstract, muxserve_abstract, parrot_abstract

class ResearchListenerGroup:
    def __init__(self, research_listeners, num_papers, email_recipients, title):
        self.research_listeners = research_listeners
        self.num_papers = num_papers
        self.email_recipients = email_recipients
        self.title = title

class ResearchListener:
    def __init__(self, title, text):
        self.title = title
        self.text = text

research_listeners = [
    ResearchListener(
        "Autellix",
        autellix_abstract,
    ),
    ResearchListener(
        "MuxServe",
        muxserve_abstract,
    ),
    ResearchListener(
        "Parrot",
        parrot_abstract,
    ),
]

research_listener_group = ResearchListenerGroup(
    research_listeners,
    10,
    ["otto.white20@imperial.ac.uk",
     "whiteotto4@gmail.com",
     "marcel.wagenlander19@imperial.ac.uk",
     "yt522@ic.ac.uk"],
    "Inference-time / agentic project"
)

test_research_listener_group = ResearchListenerGroup(
    research_listeners,
    3,
    ["otto.white20@imperial.ac.uk"],
    "Test project"
)