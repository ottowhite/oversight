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
    ResearchListener(
        "SGLang",
        "Large language models (LLMs) are increasingly used for complex tasks that require multiple generation calls, advanced prompting techniques, control flow, and structured inputs/outputs. However, efficient systems are lacking for programming and executing these applications. We introduce SGLang, a system for efficient execution of complex language model programs. SGLang consists of a frontend language and a runtime. The frontend simplifies programming with primitives for generation and parallelism control. The runtime accelerates execution with novel optimizations like RadixAttention for KV cache reuse and compressed finite state machines for faster structured output decoding. Experiments show that SGLang achieves up to 6.4x higher throughput compared to state-of-the-art inference systems on various large language and multi-modal models on tasks including agent control, logical reasoning, few-shot learning benchmarks, JSON decoding, retrieval-augmented generation pipelines, and multi-turn chat. The code is publicly available at this https URL"
    )
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
    10,
    ["otto.white20@imperial.ac.uk"],
    "Test project"
)