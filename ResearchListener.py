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
        "Large-scale language-model (LM) applications now resemble distributed programs whose interactive “agentic” workflows are governed by service-level objectives (SLOs) that users experience at sub-second granularity. Existing schedulers optimise only the end-to-end deadline of the entire LM program, ignoring the time-between-consumable chunks (TBC) that determines perceived responsiveness and opportunities to cancel misbehaving runs. We present SCALE (SLO-Conscious Adaptive Latency-and-Efficiency scheduler), the first runtime that jointly optimises throughput and fine-grained latency for LM programs. SCALE models each program component—including conditional branches—and predicts its execution time on heterogeneous accelerators. Given a per-component SLO budget, SCALE formulates scheduling as a constrained optimisation that maximises global throughput while guaranteeing that every TBC (and, optionally, the overall deadline) is met. A prototype of SCALE deployed on a 128-GPU cluster supports both inference-time agent workflows and training-time self-reflection loops. Across nine production-style LM workloads, SCALE sustains up to 2.3× higher job throughput than a latency-agnostic baseline while meeting 99.9 % of TBC SLOs; compared with an end-to-end-only SLO scheduler, it reduces median interactive latency by up to 4.7× without losing cluster utilisation. These results demonstrate that SLO-aware, mixed latency/throughput optimisation is essential for the next generation of LM systems, providing a complete picture for both end users and datacentre operators.",
    ),
    ResearchListener(
        "Tempo",
        "Large-scale language-model (LM) applications now resemble distributed programs whose interactive “agentic” workflows are governed by service-level objectives (SLOs) that users experience at sub-second granularity. Existing schedulers optimise only the end-to-end deadline of the entire LM program, ignoring the time-between-consumable chunks (TBC) that determines perceived responsiveness and opportunities to cancel misbehaving runs. We present SCALE (SLO-Conscious Adaptive Latency-and-Efficiency scheduler), the first runtime that jointly optimises throughput and fine-grained latency for LM programs. SCALE models each program component—including conditional branches—and predicts its execution time on heterogeneous accelerators. Given a per-component SLO budget, SCALE formulates scheduling as a constrained optimisation that maximises global throughput while guaranteeing that every TBC (and, optionally, the overall deadline) is met. A prototype of SCALE deployed on a 128-GPU cluster supports both inference-time agent workflows and training-time self-reflection loops. Across nine production-style LM workloads, SCALE sustains up to 2.3× higher job throughput than a latency-agnostic baseline while meeting 99.9 % of TBC SLOs; compared with an end-to-end-only SLO scheduler, it reduces median interactive latency by up to 4.7× without losing cluster utilisation. These results demonstrate that SLO-aware, mixed latency/throughput optimisation is essential for the next generation of LM systems, providing a complete picture for both end users and datacentre operators."
    ),
]

# TODO: Add this back
# ["otto.white20@imperial.ac.uk", "whiteotto4@gmail.com", "marcelw@meta.com", "marcel.wagenlander19@imperial.ac.uk"]

research_listener_group = ResearchListenerGroup(
    research_listeners,
    10,
    ["otto.white20@imperial.ac.uk"],
    "Inference-time / agentic project"
)