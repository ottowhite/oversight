# 67 Papers

## [LithOS: An Operating System for Efficient Machine Learning on GPUs](https://dl.acm.org/doi/10.1145/3731569.3764818)

**DOI:** `10.1145/3731569.3764818`

**Authors:**

- Patrick H. Coppock (*Carnegie Mellon University*)
- Brian Zhang (*Carnegie Mellon University*)
- Eliot H. Solomon (*Carnegie Mellon University*)
- Vasileios Kypriotis (*Carnegie Mellon University*)
- Leon Yang (*Meta*)
- Bikash Sharma (*Meta*)
- Dan Schatzberg (*Meta*)
- Todd C. Mowry (*Carnegie Mellon University*)
- Dimitrios Skarlatos (*Carnegie Mellon University*)

**Abstract:**

> The rapid growth of machine learning (ML) has made GPUs indispensable in datacenters and underscores the urgency of improving their efficiency. However, balancing diverse model demands with high utilization remains a fundamental challenge. Transparent, fine-grained GPU resource management that maximizes utilization, energy efficiency, and isolation requires an OS approach. This paper introduces LithOS, a first step towards a GPU OS. LithOS includes the following new abstractions and mechanisms for efficient GPU management: (i) a novel TPC Scheduler that supports spatial scheduling at the granularity of individual TPCs, unlocking efficient TPC stealing between workloads; (ii) a transparent kernel atomizer to reduce head-of-line blocking and allow dynamic resource reallocation mid-execution; (iii) a lightweight hardware right-sizing mechanism that dynamically determines the minimal TPC resources needed per atom; and (iv) a transparent power management mechanism that reduces power consumption based upon in-flight work characteristics. We build LithOS in Rust and evaluate its performance across a broad set of deep learning environments, comparing it to state-of-the-art solutions from NVIDIA and prior research. For inference stacking, LithOS reduces tail latencies by 13× compared to MPS; compared to the best-performing SotA, it reduces tail latencies by 4× while improving aggregate goodput by 1.3×. Furthermore, in hybrid inference-training stacking, LithOS reduces tail latencies by 4.7× compared to MPS; compared to the best-performing SotA, it reduces tail latencies by 1.18× while improving aggregate throughput by 1.35×. Finally, for a modest performance hit under 4%, LithOS's hardware right-sizing provides a quarter of GPU capacity savings on average, while for a 7% hit, LithOS's transparent power management delivers a quarter of GPU total energy savings on average. Overall, LithOS transparently increases GPU efficiency, establishing a foundation for future OS research on GPUs.

---

## [μFork: Supporting POSIX fork Within a Single-Address-Space OS](https://dl.acm.org/doi/10.1145/3731569.3764809)

**DOI:** `10.1145/3731569.3764809`

**Authors:**

- John Alistair Kressel (*The University of Manchester*)
- Hugo Lefeuvre (*The University of British Columbia*)
- Pierre Olivier (*The University of Manchester*)

**Abstract:**

> Single-address-space operating systems have well-known lightweightness benefits that result from their central design idea: the kernel and applications share a unique address space. This model makes these operating systems (OSes) incompatible by design with a large class of software: multiprocess POSIX applications. Indeed, the semantics of the primitive used to create POSIX processes, fork, are inextricably tied to the existence of multiple address spaces. Prior approaches addressing this issue trade off lightweightness, compatibility and/or isolation. We propose μFork, a single-address-space operating system design supporting POSIX fork on modern hardware without compromising on any of these key objectives. μFork emulates POSIX processes (μprocesses) and achieves fork by creating for the child a copy of the parent μprocess' memory at a different location within a single address space. This approach presents two challenges: relocating the child's absolute memory references (pointers), as well as providing user/kernel and μprocesses isolation without impacting lightweightness. We address them using CHERI. We implement μFork and evaluate it upon three real-world use-cases: Redis snapshots, Nginx multi-worker deployments, and Zygote FaaS worker warm-up. μFork outperforms previous work and traditional monolithic OSes on key lightweightness metrics by an order of magnitude, e.g. it can offer a fork-bound FaaS function throughput 24% higher than that of a monolithic OS, and can fork a μprocess in 54 μs, 3.7× faster than a traditional fork.

---

## [Tock: From Research To Securing 10 Million Computers](https://dl.acm.org/doi/10.1145/3731569.3764828)

**DOI:** `10.1145/3731569.3764828`

**Authors:**

- Leon Schuermann (*Princeton University*)
- Brad Campbell (*University of Virginia*)
- Branden Ghena (*Northwestern University*)
- Philip Levis (*Stanford University*)
- Amit Levy (*Princeton University*)
- Pat Pannuto (*University of California, San Diego*)

**Abstract:**

> Tock began 10 years ago as a research operating system developed by academics to help other academics build urban sensing applications. By leveraging a new language (Rust) and new hardware protection mechanisms, Tock enabled "Multiprogramming a 64 kB Computer Safely and Efficiently". Today, it is an open-source project with a vibrant community of users and contributors. It is deployed on root-of-trust hardware in data-center servers and on millions of laptops; it is used to develop automotive and space products, wearable electronics, and hardware security tokens—all while remaining a platform for operating systems research. This paper focuses on the impact of Tock's technical design on its adoption, the challenges and unexpected benefits of using a type-safe language (Rust)—particularly in security-sensitive settings—and the experience of supporting a production open-source operating system from academia.

---

## [Proto: A Guided Journey through Modern OS Construction](https://dl.acm.org/doi/10.1145/3731569.3764811)

**DOI:** `10.1145/3731569.3764811`

**Authors:**

- Wonkyo Choe (*University of Virginia*)
- Rongxiang Wang (*University of Virginia*)
- Afsara Benazir (*University of Virginia*)
- Felix Xiaozhu Lin (*University of Virginia*)

**Abstract:**

> Proto is a new instructional OS that runs on commodity, portable hardware. It showcases modern features, including per-app address spaces, threading, commodity filesystems, USB, DMA, multicore support, self-hosted debugging, and a window manager. It supports rich applications such as 2D/3D games, music and video players, and a blockchain miner. Unlike traditional instructional systems, Proto emphasizes engaging, media-rich apps that go beyond basic terminal programs. Our method breaks down a full-featured OS into a set of incremental, self-contained prototypes. Each prototype introduces a minimal set of OS mechanisms, driven by the needs of specific apps. The construction process then progressively enables these apps by bringing up one mechanism at a time. Proto enables a wider audience to experience building a self-contained software system used in daily life.

---

## [CHERIoT RTOS: An OS for Fine-Grained Memory-Safe Compartments on Low-Cost Embedded Devices](https://dl.acm.org/doi/10.1145/3731569.3764844)

**DOI:** `10.1145/3731569.3764844`

**Authors:**

- Saar Amar (*Apple*)
- Tony Chen (*Microsoft*)
- David Chisnall (*SCI Semiconductor*)
- Nathaniel Wesley Filardo (*SCI Semiconductor*)
- Ben Laurie (*Google*)
- Hugo Lefeuvre (*The University of British Columbia*)
- Kunyan Liu (*Microsoft*)
- Simon W. Moore (*University of Cambridge*)
- Robert Norton-Wright (*SCI Semiconductor*)
- Margo Seltzer (*The University of British Columbia*)
- Yucong Tao (*Microsoft*)
- Robert N. M. Watson (*University of Cambridge*)
- Hongyan Xia (*ARM Ltd.*)

**Abstract:**

> Embedded systems do not benefit from strong memory protection, because they are designed to minimize cost. At the same time, there is increasing pressure to connect embedded devices to the internet, where their vulnerable nature makes them routinely subject to compromise. This fundamental tension leads to the current status-quo where exploitable devices put individuals and critical infrastructure at risk. We present the design of a dependable embedded OS where compartmentalization and memory safety are first-class citizens. We co-design the OS with an embedded hardware platform that implements CHERI capabilities at a similar cost profile to existing chips with minimal security. We demonstrate key design benefits: fine-grained fault-tolerant compartments, OS-level support for compartment-interface hardening, and auditing facilities to thwart supply-chain attacks, among others, and show that they come at a memory usage and performance cost that allows their widespread deployment in cheap, resource-constrained devices.

---

## [The Design and Implementation of a Virtual Firmware Monitor](https://dl.acm.org/doi/10.1145/3731569.3764826)

**DOI:** `10.1145/3731569.3764826`

**Authors:**

- Charly Castes (*EPFL*)
- François Costa (*ETH Zurich*)
- Neelu S. Kalani (*EPFL*)
- Timothy Roscoe (*ETH Zurich*)
- Nate Foster (*Cornell and Jane Street*)
- Thomas Bourgeat (*EPFL*)
- Edouard Bugnion (*EPFL*)

**Abstract:**

> Low level software is often granted high privilege, yet this need not be the case. Although vendor firmware plays a critical role in the operation and management of the machine, most of its functionality does not require unfettered access to security critical software and data. In this paper we demonstrate that vendor firmware can be safely and efficiently deprivileged, decoupling its functionality from isolation enforcement. We introduce a new class of systems, called virtual firmware monitors, that run unmodified vendor firmware in userspace through software-based virtualization of the highest privilege mode of the application CPU. We describe the implementation of Miralis, a RISC-V virtual firmware monitor, and develop three security policies to protect the OS, enclaves, and confidential VMs from malicious firmware. We verify key components of Miralis, such as instruction emulation and memory protection, through exhaustive symbolic execution. Finally, we demonstrate that Miralis can effectively virtualize unmodified vendor firmware for two hardware platforms with no performance degradation compared to native execution.

---

## [Oasis: Pooling PCIe Devices Over CXL to Boost Utilization](https://dl.acm.org/doi/10.1145/3731569.3764812)

**DOI:** `10.1145/3731569.3764812`

**Authors:**

- Yuhong Zhong (*Columbia University*)
- Daniel S. Berger (*Microsoft Azure and University of Washington*)
- Pantea Zardoshti (*Microsoft Azure*)
- Enrique Saurez (*Microsoft Azure*)
- Jacob Nelson (*Microsoft Research*)
- Dan R. K. Ports (*Microsoft Research*)
- Antonis Psistakis (*University of Illinois Urbana-Champaign*)
- Joshua Fried (*MIT CSAIL*)
- Asaf Cidon (*Columbia University*)

**Abstract:**

> PCIe devices, such as NICs and SSDs, are frequently underutilized in cloud platforms. PCIe device pools, in which multiple hosts can share a set of PCIe devices, could increase PCIe device utilization and reduce their total cost of ownership. The main way to achieve PCIe device pools today is via PCIe switches, but they are expensive and inflexible. We design Oasis,1 a system that pools PCIe devices in software over CXL memory pools. CXL memory pools are already being deployed to boost datacenter memory utilization and reduce costs. Once CXL pools are in place, they can serve as an efficient data path between hosts and PCIe devices. Oasis provides a control plane and datapath over CXL pools, mapping and routing PCIe device traffic across host boundaries. PCIe devices with different functionalities can be supported by adding an Oasis engine for each device class. We implement an Oasis network engine to demonstrate NIC pooling. Our evaluation shows that Oasis improves the NIC utilization by 2× and handles NIC failover with only a 38 ms interruption.

---

## [Spirit: Fair Allocation of Interdependent Resources in Remote Memory Systems](https://dl.acm.org/doi/10.1145/3731569.3764805)

**DOI:** `10.1145/3731569.3764805`

**Authors:**

- Seung-seob Lee (*Yale University*)
- Jachym Putta (*Yale University*)
- Ziming Mao (*UC Berkeley*)
- Anurag Khandelwal (*Yale University*)

**Abstract:**

> We address the problem of fair resource allocation in multiuser remote memory systems. Allocating local memory (used as cache) and network bandwidth to remote memory in such systems is challenging due to the complex interdependence between the two resources and application performance. A larger cache may reduce the need for fetching data over the network, while a larger bandwidth may permit more concurrent network requests, avoiding the need for large caches. As a result, applications can achieve the same data access throughput for a wide range of cache and bandwidth allocations. Such interdependence is unique to each application and hard to capture offline. We propose Spirit, a multi-user framework for fair resource allocation in remote memory systems. Spirit employs a novel Symbiosis algorithm rooted in microeconomic theory that takes application-specific dependency between cache and network bandwidth into account and 'trades' cache and bandwidth resources across users at runtime. We show, both theoretically and empirically, that Symbiosis allocations across users achieve strong fairness properties. Additionally, compared to traditional resource allocation schemes, Spirit improves performance by up to 21.6% across tens of real-world applications with diverse resource needs.

---

## [Scalable Far Memory: Balancing Faults and Evictions](https://dl.acm.org/doi/10.1145/3731569.3764842)

**DOI:** `10.1145/3731569.3764842`

**Authors:**

- Yueyang Pan (*EPFL*)
- Yash Lala (*Yale University*)
- Musa Unal (*EPFL*)
- Yujie Ren (*EPFL*)
- Seung-seob Lee (*Yale University*)
- Abhishek Bhattacharjee (*Yale University*)
- Anurag Khandelwal (*Yale University*)
- Sanidhya Kashyap (*EPFL*)

**Abstract:**

> Page-based far memory systems transparently expand an application's memory capacity beyond a single machine without modifying application code. However, existing systems are tailored to scenarios with low application thread counts, and fail to scale on today's multi-core machines. This makes them unsuitable for data-intensive applications that both rely on far memory support and scale with increasing thread count. Our analysis reveals that this poor scalability stems from inefficient holistic coordination between page fault-in and eviction operations. As thread count increases, current systems encounter scalability bottlenecks in TLB shootdowns, page accounting, and memory allocation. This paper presents three design principles that address these scalability challenges and enable efficient memory offloading. These principles are always-asynchronous decoupling to handle eviction operations as asynchronously as possible, cross-batch pipelined execution to avoid idle waiting periods, and scalability prioritization to avoid synchronization overheads at high thread counts at the cost of eviction accuracy. We implement these principles in both the Linux kernel and a library OS. Our evaluation shows that this approach increases throughput for batch-processing applications by up to 4.2× and reduces 99th percentile latency for a latency-critical memcached application by 94.5%.

---

## [Device-Assisted Live Migration of RDMA Devices](https://dl.acm.org/doi/10.1145/3731569.3764795)

**DOI:** `10.1145/3731569.3764795`

**Authors:**

- Artem Y. Polyakov (*NVIDIA Corporation*)
- Gal Shalom (*NVIDIA Corporation*)
- Asaf Schwartz (*NVIDIA Corporation*)
- Aviad Yehezkel (*NVIDIA Corporation*)
- Omri Ben David (*NVIDIA Corporation*)
- Omri Kahalon (*NVIDIA Corporation*)
- Ariel Shahar (*NVIDIA Corporation*)
- Liran Liss (*NVIDIA Corporation*)

**Abstract:**

> Recently, we have seen growing pressure to move highperformance workloads, such as HPC and AI, to cloud environments that offer more affordable and manageable infrastructure. These workloads require direct access to RDMA devices for high-performance communication. Device passthrough, however, violates the decoupling between the guest OS and the underlying hardware, making Live Migration (LM) extremely challenging [29, 38, 40, 42, 48]. This paper presents a method for migrating a collection of directly interacting hardware devices in a manner that is transparent to both the VM and its network peers. We propose a device-assisted solution that includes (a) a generic device-hypervisor interface, (b) the design and implementation of LM support for the NVIDIA ConnectX family of network adapters, and (c) a novel scheme to quiesce direct communication over the memory fabric (e.g., PCIe). We demonstrate transparent migration of HPC and AI workloads in accelerated virtual environments. Our approach incurs no runtime overhead or performance degradation after migration and achieves sub-second downtimes even for VMs with high RDMA resource utilization.

---

## [Demeter: A Scalable and Elastic Tiered Memory Solution for Virtualized Cloud via Guest Delegation](https://dl.acm.org/doi/10.1145/3731569.3764801)

**DOI:** `10.1145/3731569.3764801`

**Authors:**

- Junliang Hu (*The Chinese University of Hong Kong*)
- Zhisheng Hu (*The Chinese University of Hong Kong*)
- Chun-Feng Wu (*National Yang Ming Ciao Tung University*)
- Ming-Chang Yang (*The Chinese University of Hong Kong*)

**Abstract:**

> Memory scalability has emerged as a critical bottleneck in virtualized cloud environments. Tiered memory architectures that combine limited fast memory with abundant slower memory offer a promising solution, but existing hypervisor-based approaches suffer from significant performance penalties. We present Demeter, introducing a paradigm shift through guest-delegated tiered memory management based on two key insights: (1) delegation to guests eliminates both expensive access tracking at the hypervisor level and frequent TLB flushes that severely degrade memory virtualization performance under two-dimensional address translation, and (2) Processor Event-Based Sampling, which cannot be effectively utilized by hypervisor-based solutions, remains fully functional and highly efficient when properly leveraged within the guest. Building on these insights, Demeter designs an efficient range-based tiered memory management scheme in guest virtual address space to preserve locality information and employs a double balloon-based provisioning mechanism that maintains cloud elasticity while enabling vendor-specific QoS control. Our evaluation with seven real-world workloads across DRAM+PMEM and DRAM+CXL.mem configurations demonstrates that Demeter improves performance by up to 2× compared to existing hypervisor-based approaches and by 28% on average compared to the next best guest-based alternative. Our implementation is fully open source and publicly available at Zenodo.

---

## [Robust LLM Training Infrastructure at ByteDance](https://dl.acm.org/doi/10.1145/3731569.3764838)

**DOI:** `10.1145/3731569.3764838`

**Authors:**

- Borui Wan (*The University of Hong Kong*)
- Gaohong Liu (*ByteDance Seed*)
- Zuquan Song (*ByteDance Seed*)
- Jun Wang (*ByteDance Seed*)
- Yun Zhang (*ByteDance Seed*)
- Guangming Sheng (*The University of Hong Kong*)
- Shuguang Wang (*ByteDance Seed*)
- Houmin Wei (*ByteDance Seed*)
- Chenyuan Wang (*ByteDance Seed*)
- Weiqiang Lou (*ByteDance Seed*)
- Xi Yang (*ByteDance Seed*)
- Mofan Zhang (*ByteDance Seed*)
- Kaihua Jiang (*ByteDance Seed*)
- Cheng Ren (*ByteDance Seed*)
- Xiaoyun Zhi (*ByteDance Seed*)
- Menghan Yu (*ByteDance Seed*)
- Zhuolin Zheng (*ByteDance Seed*)
- Zhe Nan (*ByteDance Seed*)
- Baoquan Zhong (*ByteDance Seed*)
- Qinlong Wang (*ByteDance Seed*)
- Huan Yu (*ByteDance Seed*)
- Jinxin Chi (*ByteDance Seed*)
- Wang Zhang (*ByteDance Seed*)
- Yuhan Li (*ByteDance Seed*)
- Zixian Du (*ByteDance Seed*)
- Sida Zhao (*ByteDance Seed*)
- Yongqiang Zhang (*ByteDance Seed*)
- Jingzhe Tang (*ByteDance Seed*)
- Zherui Liu (*ByteDance Seed*)
- Chuan Wu (*The University of Hong Kong*)
- Yanghua Peng (*ByteDance Seed*)
- Haibin Lin (*ByteDance Seed*)
- Wencong Xiao (*ByteDance Seed*)
- Xin Liu (*ByteDance Seed*)
- Liang Xiang (*ByteDance Seed*)

**Abstract:**

> The training scale of large language models (LLMs) has reached tens of thousands of GPUs and is still continuously expanding, enabling faster learning of larger models. Accompanying the expansion of the resource scale is the prevalence of failures (CUDA error, NaN values, job hang, etc.), which poses significant challenges to training stability. Any large-scale LLM training infrastructure should strive for minimal training interruption, efficient fault diagnosis, and effective failure tolerance to enable highly efficient continuous training. This paper presents ByteRobust, a large-scale GPU infrastructure management system tailored for robust and stable training of LLMs. It exploits the uniqueness of LLM training process and gives top priorities to detecting and recovering failures in a routine manner. Leveraging parallelisms and characteristics of LLM training, ByteRobust enables high-capacity fault tolerance, prompt fault demarcation, and localization with an effective data-driven approach, comprehensively ensuring continuous and efficient training of LLM tasks. ByteRobust is deployed on a production GPU platform and advances the state of the art in training robustness by achieving 97% ETTR for a three-month training job on 9,600 GPUs.

---

## [Sailor: Automating Distributed Training over Dynamic, Heterogeneous, and Geo-distributed Clusters](https://dl.acm.org/doi/10.1145/3731569.3764839)

**DOI:** `10.1145/3731569.3764839`

**Authors:**

- Foteini Strati (*ETH Zurich*)
- Zhendong Zhang (*ETH Zurich*)
- George Manos (*ETH Zurich*)
- Ixeia Sánchez Périz (*unaffiliated*)
- Qinghao Hu (*MIT*)
- Tiancheng Chen (*ETH Zurich*)
- Berk Buzcu (*HES-SO*)
- Song Han (*MIT*)
- Pamela Delgado (*HES-SO*)
- Ana Klimovic (*ETH Zurich*)

**Abstract:**

> The high GPU demand of ML training makes it hard to allocate large homogeneous clusters of high-end GPUs in a single availability zone. Leveraging heterogeneous GPUs available within and across zones can improve throughput at a reasonable cost. However, training ML models on heterogeneous resources introduces significant challenges, such as stragglers and a large search space of possible job configurations. Current systems lack support for efficiently training models on heterogeneous resources. We present Sailor, a system that automates distributed training over heterogeneous, geo-distributed, and dynamically available resources. Sailor combines an efficient search space exploration algorithm, accurate runtime and memory footprint simulation, and a distributed training framework that supports different types of heterogeneity to optimize training throughput and cost.

---

## [DCP: Addressing Input Dynamism In Long-Context Training via Dynamic Context Parallelism](https://dl.acm.org/doi/10.1145/3731569.3764849)

**DOI:** `10.1145/3731569.3764849`

**Authors:**

- Chenyu Jiang (*The University of Hong Kong*)
- Zhenkun Cai (*Amazon Web Services, Inc.*)
- Ye Tian (*The University of Hong Kong*)
- Zhen Jia (*Amazon Web Services, Inc.*)
- Yida Wang (*Amazon Web Services, Inc.*)
- Chuan Wu (*The University of Hong Kong*)

**Abstract:**

> Context parallelism has emerged as a key technique to support long-context training, a growing trend in generative AI for modern large models. However, existing context parallel methods rely on static parallelization configurations that overlook the dynamic nature of training data, specifically, the variability in sequence lengths and token relationships (i.e., attention patterns) across samples. As a result, these methods often suffer from unnecessary communication overhead and imbalanced computation. In this paper, we present DCP, a dynamic context parallel training framework that introduces fine-grained blockwise partitioning of both data and computation. By enabling flexible mapping of data and computation blocks to devices, DCP can adapt to varying sequence characteristics, effectively reducing communication and improving memory and computation balance. Micro-benchmarks demonstrate that DCP accelerates attention by 1.19x~2.45x under causal masks and 2.15x~3.77x under sparse attention patterns. Additionally, we observe up to 0.94x~1.16x end-to-end training speed-up for causal masks, and 1.00x~1.46x for sparse masks.

---

## [TrainVerify: Equivalence-Based Verification for Distributed LLM Training](https://dl.acm.org/doi/10.1145/3731569.3764850)

**DOI:** `10.1145/3731569.3764850`

**Authors:**

- Yunchi Lu (*University of Michigan*)
- Youshan Miao (*Microsoft Research*)
- Cheng Tan (*Northeastern University*)
- Peng Huang (*University of Michigan*)
- Yi Zhu (*Microsoft Research*)
- Xian Zhang (*Microsoft Research*)
- Fan Yang (*Microsoft Research*)

**Abstract:**

> Training large language models (LLMs) at scale requires parallel execution across thousands of devices, incurring enormous computational costs. Yet, these costly distributed trainings are prone to correctness bugs, causing silent errors and potentially wasting millions of GPU hours. These bugs are challenging to expose through testing. We introduce TrainVerify, a system for verifiable distributed training of LLMs to eliminate parallelization bugs. Given a deep learning model's logical specification as the ground truth, TrainVerify formally verifies that a distributed parallel execution plan is mathematically equivalent to it. Direct verification is notoriously difficult due to the sheer scale of LLMs which often involves billions of variables and highly intricate computation graphs. Therefore, TrainVerify introduces a stage-wise parallel verification algorithm and shape-reduction techniques that significantly reduce complexity while preserving formal correctness. TrainVerify scales to frontier LLMs, including the successful verification of the Llama3 405B and DeepSeek-V3 671B training plans.

---

## [Mycroft: Tracing Dependencies in Collective Communication Towards Reliable LLM Training](https://dl.acm.org/doi/10.1145/3731569.3764848)

**DOI:** `10.1145/3731569.3764848`

**Authors:**

- Yangtao Deng (*The Chinese University of Hong Kong*)
- Lei Zhang (*ByteDance*)
- Qinlong Wang (*ByteDance Seed*)
- Xiaoyun Zhi (*ByteDance Seed*)
- Xinlei Zhang (*ByteDance*)
- Zhuo Jiang (*ByteDance*)
- Haohan Xu (*ByteDance*)
- Lei Wang (*ByteDance*)
- Zuquan Song (*ByteDance Seed*)
- Gaohong Liu (*ByteDance Seed*)
- Yang Bai (*ByteDance*)
- Shuguang Wang (*ByteDance Seed*)
- Wencong Xiao (*ByteDance Seed*)
- Jianxi Ye (*ByteDance*)
- Minlan Yu (*Harvard University*)
- Hong Xu (*The Chinese University of Hong Kong*)

**Abstract:**

> Reliability is essential for ensuring efficiency in LLM training. However, many real-world reliability issues remain difficult to resolve, resulting in wasted resources and degraded model performance. Unfortunately, today's collective communication libraries operate as black boxes, hiding critical information needed for effective root cause analysis. We propose Mycroft, a lightweight distributed tracing and root cause analysis system designed to address previously hidden reliability issues in collective communication. Mycroft's key idea is to trace collective communication states and leverage internal control and data dependencies to resolve reliability problems in LLM training. Mycroft has been deployed at ByteDance for over six months to debug collective communication-related issues at runtime. It detected anomalies within 15 seconds in 90% of cases and identified the root cause within 20 seconds in 60% of cases. We also conducted extensive fault injection experiments to demonstrate Mycroft's capability and efficiency.

---

## [Mitigating Application Resource Overload with Targeted Task Cancellation](https://dl.acm.org/doi/10.1145/3731569.3764835)

**DOI:** `10.1145/3731569.3764835`

**Authors:**

- Yigong Hu (*Boston University*)
- Zeyin Zhang (*Johns Hopkins University*)
- Yicheng Liu (*University of Michigan & University of California, Los Angeles*)
- Yile Gu (*University of Washington*)
- Shuangyu Lei (*University of Michigan*)
- Baris Kasikci (*University of Washington*)
- Peng Huang (*University of Michigan*)

**Abstract:**

> Modern software inevitably encounters periods of resource overload, during which it must still sustain high servicelevel objective (SLO) attainment while minimizing request loss. However, achieving this balance is challenging due to subtle and unpredictable internal resource contention among concurrently executing requests. Traditional overload control mechanisms, which rely on global signals, such as queuing delays, fail to handle application resource overload effectively because they cannot accurately predict which requests will monopolize critical resources. In this paper, we propose Atropos, an overload control framework that proactively cancels the culprit request that cause severe resource contention rather than the victim requests that are blocked by it. Atropos continuously monitors the resource usage of executing requests, identifies the requests contributing most significantly to resource overload, and selectively cancels them. We integrate Atropos into six large-scale applications and evaluate it against 16 real-world overload scenarios. Our results show that Atropos maintains the performance goals while achieving minimal request drop, significantly outperforming state-of-the-art solutions.

---

## [Orthrus: Efficient and Timely Detection of Silent User Data Corruption in the Cloud with Resource-Adaptive Computation Validation](https://dl.acm.org/doi/10.1145/3731569.3764832)

**DOI:** `10.1145/3731569.3764832`

**Authors:**

- Chenxiao Liu (*University of Chinese Academy of Sciences*)
- Zhenting Zhu (*UCLA*)
- Quanxi Li (*University of Chinese Academy of Sciences*)
- Yanwen Xia (*University of Chinese Academy of Sciences*)
- Yifan Qiao (*UC Berkeley*)
- Xiangyun Deng (*Peking University*)
- Youyou Lu (*Tsinghua University*)
- Tao Xie (*Peking University*)
- Huimin Cui (*University of Chinese Academy of Sciences*)
- Zidong Du (*University of Chinese Academy of Sciences*)
- Harry Xu (*UCLA*)
- Chenxi Wang (*University of Chinese Academy of Sciences*)

**Abstract:**

> Even with substantial endeavors to test and validate processors, computational errors may still arise post-installation. One particular category of CPU errors transpires discreetly, without crashing applications or triggering hardware warnings. These elusive errors pose a significant threat by undermining user data, and their detection is challenging. This paper introduces Orthrus, a solution for the timely detection of silent user data corruption caused by post-installation CPU errors. Orthrus safeguards user data in cloud applications by providing simple annotations and compiler support for users to identify data operators and validating these operators asynchronously across cores while maintaining a low overhead (2%–6%), making it practical for production deployment. Our evaluation, using carefully injected errors, demonstrates that Orthrus can detect 87% of data corruptions with just a single core dedicated to validation, increasing to 91% and 96% when two and four cores are used, respectively.

---

## [Optimistic Recovery for High-Availability Software via Partial Process State Preservation](https://dl.acm.org/doi/10.1145/3731569.3764858)

**DOI:** `10.1145/3731569.3764858`

**Authors:**

- Yuzhuo Jing (*University of Michigan*)
- Yuqi Mai (*University of Michigan*)
- Angting Cai (*University of Michigan*)
- Yi Chen (*University of Michigan*)
- Wanning He (*University of Michigan*)
- Xiaoyang Qian (*University of Michigan*)
- Peter M. Chen (*University of Michigan*)
- Peng Huang (*University of Michigan*)

**Abstract:**

> Achieving high availability for modern software requires fast and correct recovery from inevitable faults. This is notoriously difficult. Existing techniques either guarantee correctness by discarding all state but suffer from long downtime, or preserve all state to recover quickly but reintroduce the fault. We present Phoenix, a framework that enables a new design point of optimistic custom recovery for high-availability software through partial process state preservation. Phoenixmode recovery allows an application to selectively preserve long-lived state, discard transient state, and reset the execution. In the common cases, it combines the effectiveness of full restart with the speed of state reuse. Phoenix offers simple APIs for annotation, supports consistency checks via unsafe region detection, and provides cross-checking validation with default recovery paths for strong correctness. We implement Phoenix in Linux kernel and apply it on six large server applications. Our extensive evaluation of real bugs and fault injection testing shows that Phoenix recovery significantly improves availability while not sacrificing correctness.

---

## [COpter: Efficient Large-Scale Resource-Allocation via Continual Optimization](https://dl.acm.org/doi/10.1145/3731569.3764846)

**DOI:** `10.1145/3731569.3764846`

**Authors:**

- Suhas Jayaram Subramanya (*Microsoft*)
- Don Kurian Dennis (*Meta*)
- Virginia Smith (*Carnegie Mellon University*)
- Gregory R. Ganger (*Carnegie Mellon University*)

**Abstract:**

> Optimization-based resource allocation in large-scale systems often must trade-off responsiveness and allocation quality. Generally, allocations are reconsidered every few minutes (a round) by formulating and solving a new optimization problem. This paper introduces continual optimization, which reframes round-based resource allocation as a sequence of interconnected problems, leveraging the observation that these resource allocation problems often only change by small amounts across successive rounds to reduce solving times. COpter provides a method for continual optimization of Linear Programs (LP) and Mixed Integer Linear Programs (MILP) formulations of resource allocation problems by combining three innovations: (1) an efficient-to-update problem representation for incremental changes, (2) a proximal-point method implementation that can provably benefit from prior computational effort and allocations, and (3) lightweight heuristics for mixed-integer problems that recover feasible integer solutions with negligible quality loss. We evaluate COpter on problems in three domains: GPU cluster scheduling, shard load balancing, and WAN traffic engineering. Overall, we find that COpter finds high-quality solutions while reducing solver runtimes by 57–83× compared to state-of-the-art commercial solvers. Compared to problem partitioning approaches (POP), COpter simultaneously improves allocation quality and reduces end-to-end allocator runtimes by 1.5–30×.

---

## [Fast End-to-End Performance Simulation of Accelerated Hardware-Software Stacks](https://dl.acm.org/doi/10.1145/3731569.3764825)

**DOI:** `10.1145/3731569.3764825`

**Authors:**

- Jiacheng Ma (*EPFL*)
- Jonas Kaufmann (Max Planck Institute for Software Systems (MPI-SWS)) (*EPFL*)
- Emilien Guandalino (*EPFL*)
- Rishabh Iyer (*UC Berkeley*)
- Thomas Bourgeat (*EPFL*)
- George Candea (*EPFL*)

**Abstract:**

> The increased use of hardware acceleration has created a need for efficient simulators of the end-to-end performance of accelerated hardware-software stacks: both software and hardware developers need to evaluate the impact of their design choices on overall system performance. However, accurate full-stack simulations are extremely slow, taking hours to simulate just 1 second of real execution. As a result, development of accelerated stacks is non-interactive, and this hurts productivity. We propose a way to simulate end-to-end performance that is orders-of-magnitude faster yet still accurate. The main idea is to take a minimalist approach: We simulate only those components of the system that are not available, and run the rest natively. Even for unavailable components, we simulate cycle-accurately only aspects that are performance-critical. The key challenge is how to correctly and efficiently synchronize the natively executing components with the simulated ones. Using this approach, we demonstrate 6× to 879× speedup compared to the state of the art, across three different hardware-accelerated stacks. The accuracy of simulated time is high: 7% error rate on average and 14% in the worst case, assuming CPU cores are not underprovisioned. Reducing simulation time down to seconds enables interactive development of accelerated stacks, which was until now not possible.

---

## [Optimizing Resource Management for Shared Microservices: A Scalable System Design](https://dl.acm.org/doi/10.1145/3631607)

**DOI:** `10.1145/3631607`

**Authors:**

- Shutian Luo (*University of Macau*)
- Chenyu Lin (*University of Macau*)
- Kejiang Ye (Shenzhen Institutes of Advanced Technology (*University of Macau*)
- Chinese Academy of Sciences) (*University of Macau*)
- Guoyao Xu (*University of Macau*)
- Liping Zhang (*University of Macau*)
- Guodong Yang (*Alibaba Group*)
- Huanle Xu (*Alibaba Group*)
- Chengzhong Xu (*University of Macau*)

**Abstract:**

> A common approach to improving resource utilization in data centers is to adaptively provision resources based on the actual workload. One fundamental challenge of doing this in microservice management frameworks, however, is that different components of a service can exhibit significant differences in their impact on end-to-end performance. To make resource management more challenging, a single microservice can be shared by multiple online services that have diverse workload patterns and SLA requirements. We present an efficient resource management system, namely Erms, for guaranteeing SLAs with high probability in shared microservice environments. Erms profiles microservice latency as a piece-wise linear function of the workload, resource usage, and interference. Based on this profiling, Erms builds resource scaling models to optimally determine latency targets for microservices with complex dependencies. Erms also designs new scheduling policies at shared microservices to further enhance resource efficiency. Experiments across microservice benchmarks as well as trace-driven simulations demonstrate that Erms can reduce SLA violation probability by 5× and more importantly, lead to a reduction in resource usage by 1.6×, compared to state-of-the-art approaches.

---

## [Diciclo: Flexible User-level Services for Efficient Multitenant Isolation](https://dl.acm.org/doi/10.1145/3639404)

**DOI:** `10.1145/3639404`

**Authors:**

- Giorgos Kappes (*University of Ioannina*)
- Stergios V. Anastasiadis (*University of Ioannina*)

**Abstract:**

> Containers are a mainstream virtualization technique for running stateful workloads over persistent storage. In highly utilized multitenant hosts, resource contention at the system kernel leads to inefficient container input/output (I/O) handling. Although there are interesting techniques to address this issue, they incur high implementation complexity and execution overhead. As a cost-effective alternative, we introduce the Diciclo architecture with our assumptions, goals, and principles. For each tenant, Diciclo isolates the control and data I/O path at user level and runs dedicated storage systems. Diciclo includes the libservice unified user-level abstraction of system services and the node structure design pattern for the application and server side. We prototyped a toolkit of user-level components that comprise the library to invoke the standard I/O calls, the I/O communication mechanism, and the I/O services. Based on Diciclo, we built Danaus, a filesystem client that integrates a union filesystem with a Ceph distributed filesystem client and configurable shared cache. Across different host configurations, workloads, and systems, Danaus achieves improved performance stability, because it handles I/O with reserved per-tenant resources and avoids intensive kernel locking. Based on having built and evaluated Danaus, we share valuable lessons about resource contention, file management, service separation, and performance stability in multitenant systems.

---

## [Characterizing Mobile SoC for Accelerating Heterogeneous LLM Inference](https://dl.acm.org/doi/10.1145/3731569.3764808)

**DOI:** `10.1145/3731569.3764808`

**Authors:**

- Le Chen (*Shanghai Jiao Tong University*)
- Dahu Feng (*Tsinghua university*)
- Erhu Feng (*Shanghai Jiao Tong University*)
- Yingrui Wang (*SenseTime*)
- Rong Zhao (*Tsinghua University*)
- Yubin Xia (*Shanghai Jiao Tong University*)
- Pinjie Xu (*SenseTime Research*)
- Haibo Chen (*Shanghai JiaoTong University*)

**Abstract:**

> With the rapid advancement of artificial intelligence technologies such as ChatGPT, AI agents, and video generation, contemporary mobile systems have begun integrating these AI capabilities on local devices to enhance privacy and reduce response latency. To meet the computational demands of AI tasks, current mobile SoCs are equipped with diverse AI accelerators, including GPUs and Neural Processing Units (NPUs). However, there has not been a comprehensive characterization of these heterogeneous processors, and existing designs typically only leverage a single AI accelerator for LLM inference, leading to suboptimal use of computational resources and memory bandwidth. In this paper, we first summarize key performance characteristics of heterogeneous processors, SoC memory bandwidth, etc. Drawing on these observations, we propose different heterogeneous parallel mechanisms to fully exploit both GPU and NPU computational power and memory bandwidth. We further design a fast synchronization mechanism between heterogeneous processors that leverages the unified memory architecture. By employing these techniques, we present HeteroInfer, the fastest LLM inference engine in mobile devices which supports GPU-NPU heterogeneous execution. Evaluation shows that HeteroInfer delivers a 1.34× to 6.02× end-to-end speedup over state-of-the-art GPU-only and NPU-only LLM engines, while maintaining negligible interference with other applications.

---

## [IC-Cache: Efficient Large Language Model Serving via In-context Caching](https://dl.acm.org/doi/10.1145/3731569.3764829)

**DOI:** `10.1145/3731569.3764829`

**Authors:**

- Yifan Yu (*University of Illinois Urbana-Champaign*)
- Yu Gan (*Google*)
- Nikhil Sarda (*Google*)
- Lillian Tsai (*Google*)
- Jiaming Shen (*Google*)
- Yanqi Zhou (*Google*)
- Arvind Krishnamurthy (*Google/Univ. of Washington*)
- Fan Lai (*University of Illinois Urbana-Champaign*)
- Hank Levy (*Google/Univ. of Washington*)
- David Culler (*Google*)

**Abstract:**

> Large language models (LLMs) have excelled in various applications, yet serving them at scale is challenging due to their substantial resource demands and high latency. Our real-world studies reveal that over 70% of user requests to LLMs have semantically similar counterparts, suggesting the potential for knowledge transfer among requests. However, naively caching and reusing past responses leads to a big quality drop. In this paper, we introduce IC-Cache, a caching system that enables live LLM capability augmentation to improve serving efficiency: by leveraging historical request-response pairs from larger models as in-context examples, IC-Cache empowers small LLMs to imitate and even exceed the compositional abilities (e.g., reasoning) of their larger counterparts, enabling selective offloading of requests to reduce cost and latency. Achieving this live augmentation at scale introduces intricate trade-offs between response quality, latency, and system throughput. For a new request, IC-Cache efficiently selects similar, high-utility examples to prepend them to the new request's input. At scale, it adaptively routes requests across LLMs of varying capabilities, accounting for response quality and serving loads. IC-Cache employs a cost-aware cache replay mechanism that refines example quality offline to maximize online cache utility and efficiency. Evaluations on millions of realistic requests demonstrate that IC-Cache improves LLM serving throughput by 1.4–5.9x and reduces latency by 28–71% without hurting response quality.

---

## [PrefillOnly: An Inference Engine for Prefill-only Workloads in Large Language Model Applications](https://dl.acm.org/doi/10.1145/3731569.3764834)

**DOI:** `10.1145/3731569.3764834`

**Authors:**

- Kuntai Du (*University of Chicago / TensorMesh, Inc.*)
- Bowen Wang (*Tsinghua University / UC Berkeley*)
- Chen Zhang (*Tsinghua University / UC Berkeley*)
- Yiming Cheng (*University of Chicago*)
- Qing Lan (*LinkedIn*)
- Hejian Sang (*LinkedIn*)
- Yihua Cheng (*University of Chicago / TensorMesh, Inc.*)
- Jiayi Yao (*University of Chicago / TensorMesh, Inc.*)
- Xiaoxuan Liu (*UC Berkeley*)
- Yifan Qiao (*UC Berkeley*)
- Ion Stoica (*UC Berkeley*)
- Junchen Jiang (*University of Chicago / TensorMesh, Inc.*)

**Abstract:**

> Besides typical generative applications, like ChatGPT, GitHub Copilot, and Cursor, we observe an emerging trend that LLMs are increasingly used in traditional discriminative tasks, such as recommendation, credit verification, and data labeling. The key characteristic of these emerging use cases is that the LLM generates only a single output token, rather than an arbitrarily long sequence of tokens. We refer to this as a prefill-only workload. However, since existing LLM engines assume arbitrary output lengths, they fail to leverage the unique properties of prefill-only workloads. In this paper, we present PrefillOnly, the first LLM inference engine that improves the inference throughput and latency by fully embracing the properties of prefill-only workloads. First, since it generates only one token, PrefillOnly only needs to store the KV cache of only the last computed layer, rather than of all layers. This drastically reduces the GPU memory footprint of LLM inference and allows handling long inputs without using solutions that reduce throughput, such as cross-GPU KV cache parallelization. Second, because the output length is fixed, rather than arbitrary, PrefillOnly can precisely determine the job completion time (JCT) of each prefill-only request before it starts. This enables efficient JCT-aware scheduling policies such as shortest prefill first. PrefillOnly can process up to 4× larger queries per second without inflating the average and P99 latency.

---

## [Pie: A Programmable Serving System for Emerging LLM Applications](https://dl.acm.org/doi/10.1145/3731569.3764814)

**DOI:** `10.1145/3731569.3764814`

**Authors:**

- In Gim (*Yale University*)
- Zhiyao Ma (*Yale University*)
- Seung-seob Lee (*Yale University*)
- Lin Zhong (*Yale University*)

**Abstract:**

> Emerging large language model (LLM) applications involve diverse reasoning strategies and agentic workflows, straining the capabilities of existing serving systems built on a monolithic token generation loop. This paper introduces Pie, a programmable LLM serving system designed for flexibility and efficiency. Pie decomposes the traditional generation loop into fine-grained service handlers exposed via an API and delegates control of the generation process to user-provided programs, called inferlets. This enables applications to implement new KV cache strategies, bespoke generation logic, and seamlessly integrate computation and I/O—entirely within the application, without requiring modifications to the serving system. Pie executes inferlets using WebAssembly, benefiting from its lightweight sandboxing. Our evaluation shows Pie matches state-of-the-art performance on standard tasks (3-12% latency overhead) while significantly improving latency and throughput (1.3×-3.4× higher) on agentic workflows by enabling application-specific optimizations.

---

## [DiffKV: Differentiated Memory Management for Large Language Models with Parallel KV Compaction](https://dl.acm.org/doi/10.1145/3731569.3764810)

**DOI:** `10.1145/3731569.3764810`

**Authors:**

- Yanqi Zhang (*Huawei*)
- Yuwei Hu (*Huawei*)
- Runyuan Zhao (*Huawei*)
- John C.S. Lui (*The Chinese University of Hong Kong*)
- Haibo Chen (*Shanghai JiaoTong University*)

**Abstract:**

> Large language models (LLMs) demonstrate remarkable capabilities but face substantial serving costs due to their high memory demands, with the key-value (KV) cache being a primary bottleneck. State-of-the-art KV cache compression techniques, such as quantization and pruning, apply uniform treatment to both keys and values, and discard unimportant tokens entirely, overlooking the fine-grained distinctions in the significance of individual KV cache components. To address such limitations, we introduce DiffKV, a novel framework for efficient KV cache compression that exploits three levels of differentiation in the KV cache: (1) the differing impact of keys and values on attention computation, (2) the varying importance of tokens, and (3) the diverse dynamic sparsity patterns across attention heads. These levels of differentiation introduce irregular memory usage patterns across different requests and attention heads, posing significant scalability challenges for memory management. To address these challenges, DiffKV proposes an on-GPU memory manager that compacts fragmented free memory list into contiguous regions in parallel, effectively translating sparsity in the KV cache into performance gains. We evaluate DiffKV on several mainstream LLMs, including the emerging thinking models that generate extended chains of thought. DiffKV is able to compress the KV cache by 2.7× to 5.7× with near-lossless accuracy on complex workloads requiring sophisticated reasoning and long-generation capabilities, and enhances throughput by 1.9× to 5.4×.

---

## [Jenga: Effective Memory Management for Serving LLM with Heterogeneity](https://dl.acm.org/doi/10.1145/3731569.3764823)

**DOI:** `10.1145/3731569.3764823`

**Authors:**

- Chen Zhang (*Tsinghua University & UC Berkeley*)
- Kuntai Du (*University of Chicago*)
- Shu Liu (*UC Berkeley*)
- Woosuk Kwon (*UC Berkeley*)
- Xiangxi Mo (*UC Berkeley*)
- Yufeng Wang (*Independent Researcher*)
- Xiaoxuan Liu (*UC Berkeley*)
- Kaichao You (*Tsinghua University*)
- Zhuohan Li (*UC Berkeley*)
- Mingsheng Long (*Tsinghua University*)
- Jidong Zhai (*Tsinghua University*)
- Joseph Gonzalez (*UC Berkeley*)
- Ion Stoica (*UC Berkeley*)

**Abstract:**

> Large language models are widely used but expensive to run. To reduce costs, it is crucial to maximize request batch size through efficient GPU memory management. Existing approaches, such as PagedAttention, struggle with modern LLMs because of the growing heterogeneity in the sizes of models' internal embeddings and attention mechanisms. In this paper, we present Jenga, a memory allocation framework for these heterogeneous LLMs. Jenga tackles two key challenges: (1) memory fragmentation caused by embeddings of different sizes, and (2) unpredictable memory usage from varying attention mechanisms across layers. Jenga employs an attention-property-aware allocator, leveraging the least common multiple (LCM) of embedding sizes to optimize memory usage and performing cache eviction based on attention patterns to enhance memory reuse. We implement Jenga in vLLM, and evaluate it with diverse LLMs, datasets, and GPUs. Evaluations show that Jenga improves GPU memory utilization by up to 83% and serving throughput by up to 2.16× (1.46× on average).

---

## [cache_ext: Customizing the Page Cache with eBPF](https://dl.acm.org/doi/10.1145/3731569.3764820)

**DOI:** `10.1145/3731569.3764820`

**Authors:**

- Tal Zussman (*Columbia University*)
- Ioannis Zarkadas (*Columbia University*)
- Jeremy Carin (*Columbia University*)
- Andrew Cheng (*Columbia University*)
- Hubertus Franke (*IBM Research*)
- Jonas Pfefferle (*IBM Research*)
- Asaf Cidon (*Columbia University*)

**Abstract:**

> The OS page cache is central to the performance of many applications, by reducing excessive accesses to storage. However, its one-size-fits-all eviction policy performs poorly in many workloads. While the systems community has experimented with a plethora of new and adaptive eviction policies in non-OS settings (e.g., key-value stores, CDNs), it is very difficult to implement such policies in the page cache, due to the complexity of modifying kernel code. To address these shortcomings, we design a flexible eBPF-based framework for the Linux page cache, called cache_ext, that allows developers to customize the page cache without modifying the kernel. cache_ext enables applications to customize the page cache policy for their specific needs, while also ensuring that different applications' policies do not interfere with each other and preserving the page cache's ability to share memory across different processes. We demonstrate the flexibility of cache_ext's interface by using it to implement eight different policies, including sophisticated eviction algorithms. Our evaluation shows that it is indeed beneficial for applications to customize the page cache to match their workloads' unique properties, and that they can achieve up to 70% higher throughput and 58% lower tail latency.

---

## [Aeolia: A Fast and Secure Userspace Interrupt-Based Storage Stack](https://dl.acm.org/doi/10.1145/3731569.3764816)

**DOI:** `10.1145/3731569.3764816`

**Authors:**

- Chuandong Li (*Peking University and Zhongguancun Laboratory*)
- Ran Yi (*Peking University*)
- Zonghao Zhang (*Peking University and Zhongguancun Laboratory*)
- Jing Liu (*Microsoft Research*)
- Changwoo Min (*Igalia*)
- Jie Zhang (*Peking University and Zhongguancun Laboratory*)
- Yingwei Luo (*Peking University and Zhongguancun Laboratory*)
- Xiaolin Wang (*Peking University and Zhongguancun Laboratory*)
- Zhenlin Wang (*Michigan Tech*)
- Diyu Zhou (*Peking University*)

**Abstract:**

> Polling-based userspace storage stacks achieve great I/O performance. However, they cannot efficiently and securely share disks and CPUs among multiple tasks. In contrast, interrupt-based kernel stacks inherently suffer from subpar I/O performance but achieve advantages in resource sharing. We present Aeolia, a novel storage stack that achieves great I/O performance while offering efficient and secure resource sharing. Aeolia is an interrupt-based userspace storage stack, representing a new point in the design space previously considered unfeasible. Our main observation is that, contrary to conventional wisdom, polling offers only marginal disk performance improvements over interrupts. Aeolia exploits user interrupt, an emerging hardware feature commonly used for userspace IPIs, in a novel way to deliver storage interrupts directly to userspace, thereby achieving high I/O performance with direct access. Aeolia leverages the hardware intra-process isolation features and sched_ext, an eBPF-based userspace scheduling framework, to efficiently and securely share CPUs and disks among multiple tasks, challenging the common belief that these are inherent disadvantages of userspace storage stacks. The above design enables Aeolia to realize AeoFS, a high-performance library file system that securely and directly accesses disks. Our evaluation shows that Aeolia outperforms Linux by 2× and AeoFS outperforms ext4 by up to 19.1×, respectively.

---

## [Sleeping with One Eye Open: Fast, Sustainable Storage with Sandman](https://dl.acm.org/doi/10.1145/3731569.3764804)

**DOI:** `10.1145/3731569.3764804`

**Authors:**

- Yanbo Zhou (*UC San Diego*)
- Erci Xu (*Shanghai Jiao Tong University*)
- Anisa Su (*Samsung Semiconductor*)
- Jim Harris (*Samsung Semiconductor*)
- Adam Manzanares (*Samsung Semiconductor*)
- Steven Swanson (*UC San Diego*)

**Abstract:**

> All-flash servers, while being widely popular for their high performance and large capacity, can incur significant energy consumption in modern storage systems. Through a motivational study, we discover that the culprit is the inefficiency in the software stack, and existing power-saving methods fail to deliver comparable performance, especially under workload bursts. Guided by the lessons learned, we propose Sandman, a scheduling framework that combines the fast resource scaling mechanism, resource monitoring, and I/O burst detection policies. Experiments show that Sandman reduces average power consumption by up to 39.38% and energy consumption by up to 33.36% while delivering performance comparable (within 5% in corner cases) to the best performance case (the busy-polling stack) in both benchmarks and field workloads.

---

## [Loom: Efficient Capture and Querying of High-Frequency Telemetry](https://dl.acm.org/doi/10.1145/3731569.3764853)

**DOI:** `10.1145/3731569.3764853`

**Authors:**

- Franco Solleza (*Brown University*)
- Shihang Li (*University of Washington*)
- William Sun (*Brown University*)
- Richard Tang (*Brown University*)
- Malte Schwarzkopf (*Brown University*)
- Andrew Crotty (*Northwestern University*)
- David Cohen (*Intel*)
- Nesime Tatbul (*Intel Labs and MIT*)
- Stan Zdonik (*Brown University*)

**Abstract:**

> To debug performance issues, engineers often rely on high-frequency telemetry (HFT) from sources like perf, DTrace, or eBPF, which can generate millions of records per second. Current database systems are too slow to capture such highrate data in its entirety, and the de facto standard approach of writing HFT to raw files makes queries slow and cumbersome. Engineers must therefore either work with incomplete data, which risks missing critical events, or accept slow queries. Loom is a new system specialized for capturing and analyzing HFT with timely, interactive queries. Key to Loom's design is that it combines the high ingest capability of log-based storage with lightweight, sparse, and domain-specific indexes that accelerate queries. This design strikes a balance: it prioritizes capturing complete data at high rate while indexing just enough to support interactive queries on HFT. Experiments show that Loom supports both higher ingest throughput and lower query latency than best-in-class systems for ingest-optimized storage (FishStore) and time series databases (InfluxDB), all while consuming substantially fewer host resources and ensuring data completeness.

---

## [Pesto: Cooking up High Performance BFT Queries](https://dl.acm.org/doi/10.1145/3731569.3764799)

**DOI:** `10.1145/3731569.3764799`

**Authors:**

- Florian Suri-Payer (*Cornell University*)
- Neil Giridharan (*UC Berkeley*)
- Liam Arzola (*UC San Diego*)
- Shir Cohen (*Cornell University*)
- Lorenzo Alvisi (*Cornell University*)
- Natacha Crooks (*UC Berkeley*)

**Abstract:**

> This paper presents Pesto, a high-performance Byzantine Fault Tolerant (BFT) database that offers full SQL compatibility. Pesto intentionally forgoes the use of State Machine Replication (SMR); SMR-based designs offer poor performance due to the several round trips required to order transactions. Pesto, instead, allows for replicas to remain inconsistent, and only synchronizes on demand to ensure that the database remain serializable in the presence of concurrent transactions and malicious actors. On TPC-C, Pesto matches the throughput of Peloton [20] and Postgres [21], two unreplicated SQL database systems, while increasing throughput by 2.3x compared to classic SMR-based BFT-architectures, and reducing latency by 2.7x to 3.9x. Pesto's leaderless design minimizes the impact of replica failures and ensures robust performance.

---

## [Tiga: Accelerating Geo-Distributed Transactions with Synchronized Clocks](https://dl.acm.org/doi/10.1145/3731569.3764854)

**DOI:** `10.1145/3731569.3764854`

**Authors:**

- Jinkun Geng (*Stanford University*)
- Shuai Mu (*Stony Brook University*)
- Anirudh Sivaraman (*New York University*)
- Balaji Prabhakar (*Stanford University*)

**Abstract:**

> This paper presents Tiga, a new design for geo-replicated and scalable transactional databases such as Google Spanner. Tiga aims to commit transactions within 1 wide-area roundtrip time, or 1 WRTT, for a wide range of scenarios, while maintaining high throughput with minimal computational overhead. Tiga consolidates concurrency control and consensus, completing both strictly serializable execution and consistent replication in a single round. It uses synchronized clocks to proactively order transactions by assigning each a future timestamp at submission. In most cases, transactions arrive at servers before their future timestamps and are serialized according to the designated timestamp, requiring 1 WRTT to commit. In rare cases, transactions are delayed and proactive ordering fails, in which case Tiga falls back to a slow path, committing in 1.5–2 WRTTs. Compared to state-of-the-art solutions, Tiga can commit more transactions at 1-WRTT latency, and incurs much less throughput overhead. Evaluation results show that Tiga outperforms all baselines, achieving 1.3–7.2× higher throughput and 1.4–4.6× lower latency. Tiga is open-sourced at https://github.com/New-Consensus-Concurrency-Control/Tiga.

---

## [Tempo: Compiled Dynamic Deep Learning with Symbolic Dependence Graphs](https://dl.acm.org/doi/10.1145/3731569.3764840)

**DOI:** `10.1145/3731569.3764840`

**Authors:**

- Pedro F. Silvestre (*Imperial College London*)
- Peter Pietzuch (*Imperial College London*)

**Abstract:**

> Deep learning (DL) algorithms are often defined in terms of temporal relationships: a tensor at one timestep may depend on tensors from earlier or later timesteps. Such dynamic dependencies (and corresponding dynamic tensor shapes) are difficult to express and optimize: while eager DL systems support such dynamism, they cannot apply compiler-based optimizations; graph-based systems require static tensor shapes, which forces users to pad tensors or break-up programs into multiple static graphs. We describe Tempo, a new DL system that combines the dynamism of eager execution with the whole-program optimizations of graph-based compilation. Tempo achieves this through a declarative programming model with recurrent tensors, which include explicit temporal dimensions. Temporal dimensions can be indexed using symbolic expressions to express dynamic dependencies on past and future tensors. Based on this, Tempo constructs a symbolic dependence graph, which concisely encodes dynamic dependencies between operators, and applies whole-program optimizations, such as algebraic simplifications, vectorization, tiling, and fusion. By tiling dynamic dependencies into static-size blocks, Tempo can also reuse existing static code-generators. It then uses a polyhedral model to find a feasible execution schedule, which includes memory management operations. We show that Tempo achieves a 7× speedup over JAX for Llama-3.2-3B decoding; for reinforcement learning algorithms, Tempo achieves a 54× speedup, with 16× lower peak memory usage.

---

## [SAND: A New Programming Abstraction for Video-based Deep Learning](https://dl.acm.org/doi/10.1145/3731569.3764847)

**DOI:** `10.1145/3731569.3764847`

**Authors:**

- Juncheol Ye (*KAIST*)
- Seungkook Lee (*KAIST*)
- Hwijoon Lim (*KAIST*)
- JiHyuk Lee (*Chung-Ang unversity*)
- Uitaek Hong (*KAIST*)
- Youngjin Kwon (*KAIST*)
- Dongsu Han (*KAIST*)

**Abstract:**

> Video-based deep learning (VDL) is increasingly used across diverse applications and has become highly popular, but it faces significant challenges in preprocessing highly compressed video data. Preprocessing pipelines are complex, requiring extensive engineering effort, and introduce computational bottlenecks, with latency exceeding GPU training time. Existing solutions partially mitigate these issues but remain inefficient and resource-constrained. We present SAND, a framework for VDL that integrates system-level optimizations to simplify the preprocessing pipeline and maximize resource efficiency. First, SAND introduces a view abstraction that encapsulates key preprocessing stages into virtualized objects, eliminating the need for users to manage individual objects. Second, SAND maximizes reuse opportunities through efficient system-level object management, reducing the preprocessing overhead and improving GPU utilization. Evaluation across multiple VDL applications and diverse environments, including Ray-based hyperparameter search and distributed data parallel training, shows GPU utilization improvements of up to 12.3× and 2.9× over CPU and GPU baselines, respectively, while reducing preprocessing code complexity from hundreds or thousands of lines to fewer than 10.

---

## [METIS: Fast Quality-Aware RAG Systems with Configuration Adaptation](https://dl.acm.org/doi/10.1145/3731569.3764855)

**DOI:** `10.1145/3731569.3764855`

**Authors:**

- Siddhant Ray (*University of Chicago*)
- Rui Pan (*Princeton University*)
- Zhuohan Gu (*University of Chicago*)
- Kuntai Du (*University of Chicago/ TensorMesh, Inc.*)
- Shaoting Feng (*University of Chicago*)
- Ganesh Ananthanarayanan (*Microsoft*)
- Ravi Netravali (*Princeton University*)
- Junchen Jiang (*University of Chicago/ TensorMesh, Inc.*)

**Abstract:**

> RAG (Retrieval Augmented Generation) allows LLMs (large language models) to generate better responses with external knowledge, but using more external knowledge causes higher response delay. Prior work focuses either on reducing the response delay (e.g., better scheduling of RAG queries) or on maximizing quality (e.g., tuning the RAG workflow), but they fall short in systematically balancing the tradeoff between the delay and quality of RAG responses. To balance both quality and response delay, this paper presents METIS, the first RAG system that jointly schedules queries and adapts the key RAG configurations of each query, such as the number of retrieved text chunks and synthesis methods. Using four popular RAG-QA datasets, we show that compared to the state-of-the-art RAG optimization schemes, METIS reduces the generation latency by 1.64 – 2.54× without sacrificing generation quality.

---

## [HedraRAG: Co-Optimizing Generation and Retrieval for Heterogeneous RAG Workflows](https://dl.acm.org/doi/10.1145/3731569.3764806)

**DOI:** `10.1145/3731569.3764806`

**Authors:**

- Zhengding Hu (*University of California San Diego*)
- Vibha Murthy (*University of California San Diego*)
- Zaifeng Pan (*University of California San Diego*)
- Wanlu Li (*University of California San Diego*)
- Xiaoyi Fang (*RegAilator Inc*)
- Yufei Ding (*University of California San Diego*)
- Yuke Wang (*Rice University*)

**Abstract:**

> In this paper, we identify and tackle emerging system-level challenges in serving heterogeneous RAG workflows, characterized by complex stages and diverse request patterns. We present HedraRAG, a new system built on RAGraph, a graph-based abstraction that exposes optimization opportunities across stage-level parallelism, intra-request similarity, and inter-request skewness. These opportunities are expressed through graph transformations, including node splitting, reordering, edge addition and rewiring. Transformations are dynamically applied to wavefronts of subgraphs across concurrent requests and scheduled onto the CPU-GPU pipeline. Experiments across a wide range of workflows demonstrate that HedraRAG achieves more that 1.5× and up to 5× speedup over existing frameworks, offering a comprehensive solution for heterogeneous RAG workload serving.

---

## [Coyote v2: Raising the Level of Abstraction for Data Center FPGAs](https://dl.acm.org/doi/10.1145/3731569.3764845)

**DOI:** `10.1145/3731569.3764845`

**Authors:**

- Benjamin Ramhorst (*ETH Zurich*)
- Dario Korolija (*AMD Research*)
- Maximilian Jakob Heer (*ETH Zurich*)
- Jonas Dann (*ETH Zurich*)
- Luhao Liu (*ETH Zurich*)
- Gustavo Alonso (*ETH Zurich*)

**Abstract:**

> In the trend towards hardware specialization, FPGAs play a dual role as accelerators for offloading, e.g., network virtualization, and as a vehicle for prototyping and exploring hardware designs. While FPGAs offer versatility and performance, integrating them in larger systems remains challenging. Thus, recent efforts have focused on raising the level of abstraction through better interfaces and high-level programming languages. Yet, there is still quite some room for improvement. In this paper, we present Coyote v2, an open-source FPGA shell built with a novel, three-layer hierarchical design supporting dynamic partial reconfiguration of services and user logic, with a unified logic interface, and high-level software abstractions which facilitate application deployment, multi-tenancy and transparent workload pipelining. Experimental results indicate Coyote v2 reduces synthesis times between 15% and 20% and run-time reconfiguration times by an order of magnitude, when compared to existing systems. We also demonstrate the advantages of Coyote v2 by deploying several realistic applications, including HyperLogLog cardinality estimation, AES encryption, and neural network inference. Finally, Coyote v2 places a great deal of emphasis on integration with real systems through reusable and reconfigurable services, including a fully RoCE v2-compliant networking stack, a shared virtual memory model with the host, and a DMA engine between FPGAs and GPUs. We demonstrate these features by, e.g., seamlessly deploying an FPGA-accelerated neural network from Python.

---

## [KNighter: Transforming Static Analysis with LLM-Synthesized Checkers](https://dl.acm.org/doi/10.1145/3731569.3764827)

**DOI:** `10.1145/3731569.3764827`

**Authors:**

- Chenyuan Yang (*University of Illinois at Urbana-Champaign*)
- Zijie Zhao (*University of Illinois at Urbana-Champaign*)
- Zichen Xie (*Zhejiang University*)
- Haoyu Li (*Shanghai Jiao Tong University*)
- Lingming Zhang (*University of Illinois at Urbana-Champaign*)

**Abstract:**

> Static analysis is a powerful technique for bug detection in critical systems like operating system kernels. However, designing and implementing static analyzers is challenging, time-consuming, and typically limited to predefined bug patterns. While large language models (LLMs) have shown promise for static analysis, directly applying them to scan large systems remains impractical due to computational constraints and contextual limitations. We present KNighter, the first approach that unlocks scalable LLM-based static analysis by automatically synthesizing static analyzers from historical bug patterns. Rather than using LLMs to directly analyze massive systems, our key insight is leveraging LLMs to generate specialized static analyzers guided by historical patch knowledge. KNighter implements this vision through a multi-stage synthesis pipeline that validates checker correctness against original patches and employs an automated refinement process to iteratively reduce false positives. Our evaluation on the Linux kernel demonstrates that KNighter generates high-precision checkers capable of detecting diverse bug patterns overlooked by existing human-written analyzers. To date, KNighter-synthesized checkers have discovered 92 new, critical, longlatent bugs (average 4.3 years) in the Linux kernel; 77 are confirmed, 57 fixed, and 30 have been assigned CVE numbers. This work establishes an entirely new paradigm for scalable, reliable, and traceable LLM-based static analysis for real-world systems via checker synthesis.

---

## [Fawkes: Finding Data Durability Bugs in DBMSs via Recovered Data State Verification](https://dl.acm.org/doi/10.1145/3731569.3764841)

**DOI:** `10.1145/3731569.3764841`

**Authors:**

- Zhiyong Wu (*Tsinghua University*)
- Jie Liang (*Beihang University*)
- Jingzhou Fu (*Tsinghua University*)
- Wenqian Deng (*Tsinghua University*)
- Yu Jiang (*Tsinghua University*)

**Abstract:**

> Data durability is a fundamental requirement in DBMSs, ensuring that committed data remains intact despite unexpected faults such as power failures. Despite its critical importance, implementations of durability and recovery mechanisms continue to exhibit flaws, leading to severe issues(e.g., data loss, data inconsistency), which we refer to as Data Durability Bugs (DDBs). However, there is a limited understanding of the characteristics and root causes of DDBs. Furthermore, existing testing methods(e.g., Mallory) are often inadequate for detecting DDBs, particularly those that cause data loss or data inconsistency following DBMS failures. This paper presents a comprehensive study of 43 DDBs across four widely used DBMSs. It reveals that DDBs primarily manifest as data loss, data inconsistency, log corruption, and system unavailability, often stem from flawed durability and recovery mechanisms, and are typically triggered when faults occur during filesystem or kernel-level calls. Based on these findings, we developed Fawkes, a testing framework to detect DDBs with recovered data state verification. It employs context-aware fault injection to target critical filesystem and kernel-level regions, functionality-guided fault triggering to explore untested paths, and checkpoint-based data graph verification to detect post-crash inconsistencies. We applied Fawkes to eight popular DBMSs and discovered 48 previously unknown DDBs, of which 16 have been fixed and 8 have been assigned CVE identifiers due to the severity.

---

## [Ghost in the Android Shell: Pragmatic Test-oracle Specification of a Production Hypervisor](https://dl.acm.org/doi/10.1145/3731569.3764817)

**DOI:** `10.1145/3731569.3764817`

**Authors:**

- Kayvan Memarian (*University of Cambridge*)
- Ben Simner (*University of Cambridge*)
- David Kaloper-Meršinjak (*University of Cambridge*)
- Thibaut Pérami (*University of Cambridge*)
- Peter Sewell (*University of Cambridge*)

**Abstract:**

> Developing systems code that robustly provides its intended security guarantees remains very challenging: conventional practice does not suffice, and full functional verification, while now feasible in some contexts, has substantial barriers to entry and use. In this paper, we explore an alternative, more lightweight approach to building confidence for a production hypervisor: the pKVM hypervisor developed by Google to protect virtual machines and the Android kernel from each other. The basic approach is very simple and dates back to the 1970s: we specify the desired behaviour in a way that can be used as a test oracle, and check correspondence between that and the implementation at runtime. The setting makes that challenging in several ways: the implementation and specification are intertwined with the underlying architecture; the hypervisor is highly concurrent; the specification has to be loose in certain ways; the hypervisor runs bare-metal in a privileged exception level; naive random testing would quickly crash the whole system; and the hypervisor is written in C using conventional methods. We show how all of these can be overcome to make a practically useful specification, finding a number of critical bugs in pKVM along the way. This is not at all what conventional developers (nor what formal verifiers) normally do – but we argue that, with the appropriate mindset, they easily could and should.

---

## [eBPF Misbehavior Detection: Fuzzing with a Specification-Based Oracle](https://dl.acm.org/doi/10.1145/3731569.3764797)

**DOI:** `10.1145/3731569.3764797`

**Authors:**

- Tao Lyu (*EPFL*)
- Kumar Kartikeya Dwivedi (*EPFL*)
- Thomas Bourgeat (*EPFL*)
- Mathias Payer (*EPFL*)
- Meng Xu (*University of Waterloo*)
- Sanidhya Kashyap (*EPFL*)

**Abstract:**

> Bugs in the Linux eBPF verifier may cause it to mistakenly accept unsafe eBPF programs or reject safe ones, causing either security or usability issues. While prior works on fuzzing the eBPF verifier have been effective, their bug oracles only hint at the existence of bugs indirectly (e.g., when a memory error occurs in downstream execution) instead of showing the root cause, confining them to uncover a narrow range of security bugs only with no detection of usability issues. In this paper, we propose SpecCheck, a specification-based oracle integrated with our fuzzer Veritas, to detect a wide range of bugs in the eBPF verifier. SpecCheck encodes eBPF instruction semantics and safety properties as a specification and turns the claim of whether a concrete eBPF program is safe into checking the satisfiability of the corresponding safety constraints, which can be reasoned automatically without abstraction. The output from the oracle will be crosschecked with the eBPF verifier for any discrepancies. Using SpecCheck, Veritas uncovered 13 bugs in the Linux eBPF verifier, including severe bugs that can cause privilege escalation or information leakage, as well as bugs that cause frustration in even experienced kernel developers.

---

## [WASIT: Deep and Continuous Differential Testing of WebAssembly System Interface Implementations](https://dl.acm.org/doi/10.1145/3731569.3764819)

**DOI:** `10.1145/3731569.3764819`

**Authors:**

- Yage Hu (*University of Georgia*)
- Wen Zhang (*University of Georgia*)
- Botang Xiao (*University of Georgia*)
- Qingchen Kong (*University of Georgia*)
- Boyang Yi (*University of Georgia*)
- Suxin Ji (*University of Georgia*)
- Songlan Wang (*University of Georgia*)
- Wenwen Wang (*University of Georgia*)

**Abstract:**

> This paper presents WASIT, a powerful specification-driven differential testing framework for WebAssembly (Wasm) system interface (WASI) implementations. WASIT invents several innovative techniques to address the challenges facing state-of-the-art testing approaches when applied to WASI implementations. Specifically, it introduces real-time resource abstraction and tracking to facilitate the generation of meaningful and dependent WASI function calls. It also creates a domain-specific language to automatically filter out uninteresting WASI function argument values by augmenting the WASI specification. Finally, it adopts a decoupled system architecture to achieve smooth co-evolution with WASI. Our evaluation shows that WASIT successfully found 48 new WASI-specific bugs in six popular Wasm runtimes, with 41 confirmed, 37 fixed, and three CVEs assigned.

---

## [Prove It to the Kernel: Precise Extension Analysis via Proof-Guided Abstraction Refinement](https://dl.acm.org/doi/10.1145/3731569.3764796)

**DOI:** `10.1145/3731569.3764796`

**Authors:**

- Hao Sun (*ETH Zurich*)
- Zhendong Su (*ETH Zurich*)

**Abstract:**

> Modern OS kernels, such as Linux, employ the eBPF subsystem to enable user space to extend kernel functionality. To ensure safety, an in-kernel verifier statically analyzes these extensions; however, its imprecise analysis frequently results in the erroneous rejection of safe extensions, exposing a critical tension between the precision and computational complexity of the verifier that limits kernel extensibility. We propose a proof-guided abstraction refinement technique that significantly enhances the verifier's precision while preserving low kernel space complexity. Rather than incorporating sophisticated analysis (e.g., via new abstract domains) directly into the verifier, our key insight is to decouple the complex reasoning to user space while bridging the gap through formal proofs. Upon encountering uncertainties, the verifier initiates an abstraction refinement procedure rather than rejecting the extension. As the refinement involves nontrivial reasoning, the verifier simply delineates the task and delegates it to user space. A formal proof is produced externally, which the verifier subsequently checks in linear time before adopting the refined abstraction. Consequently, our approach achieves high precision via user space reasoning while confining kernel space operations to an efficient proof check. Evaluation results show that our technique enables the verifier to accept 403 out of 512 real-world eBPF programs that were previously rejected erroneously, paving the way for more reliable and flexible kernel extensions.

---

## [Atmosphere: Practical Verified Kernels with Rust and Verus](https://dl.acm.org/doi/10.1145/3731569.3764821)

**DOI:** `10.1145/3731569.3764821`

**Authors:**

- Xiangdong Chen (*University of Utah*)
- Zhaofeng Li (*University of Utah*)
- Jerry Zhang (*University of Utah*)
- Vikram Narayanan (*Palo Alto Networks*)
- Anton Burtsev (*University of Utah*)

**Abstract:**

> Recent advances in programming languages and automated formal reasoning have changed the balance between the complexity and practicality of developing formally verified systems. Our work leverages Verus, a new verifier for Rust that combines ideas of linear types, permissioned reasoning, and automated verification based on satisfiability modulo theories (SMT), for the development of a formally verified microkernel, Atmosphere. Atmosphere is a full-featured microkernel with support for strict isolation in mixed-criticality systems. We develop all code in Rust and prove its functional correctness, i.e., refinement of a high-level specification, with Verus. Development and verification of 6K lines of executable code required an effort of less than 2.5 person-years (only 1.5 years were spent on verification, another person-year was spent developing non-verified parts of the system). On average, our code has a proof-to-code ratio of 3.32:1 and completes verification in less than 20 seconds on a modern laptop, which we argue is practical for the development of verified systems.

---

## [AutoMan: Facilitating Verified Distributed Systems Development Through Automatic Code Generation and Manual Optimizations](https://dl.acm.org/doi/10.1145/3731569.3764822)

**DOI:** `10.1145/3731569.3764822`

**Authors:**

- Zihao Zhang (*Stony Brook University*)
- Ti Zhou (*Stony Brook University*)
- Christa Jenkins (*Stony Brook University*)
- Omar Chowdhury (*Stony Brook University*)
- Shuai Mu (*Stony Brook University*)

**Abstract:**

> Developing correct and performant distributed systems is notoriously challenging due to their complexity and scale. There are two main approaches to addressing correctness issues that stem from their complexity: (i) formal verification, and (ii) automatic compilation of specifications to implementations. The former provides machine-checked correctness guarantees along with good performance but requires substantial expert effort. In contrast, the latter can reduce developer effort, though often at the expense of rigorous correctness guarantees. In this paper, we design, develop, and evaluate the AutoMan workflow, which makes developing distributed systems with refinement-based formal verification techniques more accessible and practical for both experts and developers. AutoMan achieves this by automatically generating implementations and their corresponding verification obligations from formal system specifications. This is accomplished without placing trust in the code generator and without sacrificing end-to-end correctness or performance. AutoMan's use of refinement-based verification methodology for ensuring soundness allows hand-tuned performance-critical code and automatically generated code to harmoniously co-exist without jeopardizing end-to-end correctness guarantees. The effectiveness of AutoMan is demonstrated through the reimplementation of Multi-Paxos, PBFT, a sharded Key-Value store, and CausalMesh following the AutoMan methodology. In all cases, the use of AutoMan substantially reduced development effort (e.g., 70%-97% for Multi-Paxos), while the resulting systems maintained robust efficiency and correctness.

---

## [TickTock: Verified Isolation in a Production Embedded OS](https://dl.acm.org/doi/10.1145/3731569.3764856)

**DOI:** `10.1145/3731569.3764856`

**Authors:**


**Abstract:**

> We present a case study formally verifying process isolation in the Tock production microcontroller OS kernel. Tock combines hardware memory protection units and language-level techniques—by writing the kernel in Rust—to enforce isolation between user and kernel code. Our effort to verify Tock's process abstraction unearthed multiple, subtle bugs that broke isolation—many allowing malicious applications to compromise the whole OS. We describe this effort and TickTock, our fork of the Tock operating system kernel that eliminates isolation bugs by construction. TickTock uses Flux, an SMT-based Rust verifier, to formally specify and verify process isolation for all ARMv7-M platforms Tock supports and for three RISC-V 32-bit platforms. Our verification-guided design and implementation led to a new, granular process abstraction that is simpler than Tock's, has formal security guarantees (that are verified in half a minute), and outperforms Tock on certain critical code paths.

---

## [ORQ: Complex Analytics on Private Data with Strong Security Guarantees](https://dl.acm.org/doi/10.1145/3731569.3764833)

**DOI:** `10.1145/3731569.3764833`

**Authors:**

- Eli Baum (*Boston University*)
- Sam Buxbaum (*Boston University*)
- Nitin Mathai (*The University of Texas at Austin*)
- Muhammad Faisal (*Boston University*)
- Vasiliki Kalavri (*Boston University*)
- Mayank Varia (*Boston University*)
- John Liagouris (*Boston University*)

**Abstract:**

> We present Orq, a system that enables collaborative analysis of large private datasets using cryptographically secure multi-party computation (MPC). Orq protects data against semi-honest or malicious parties and can efficiently evaluate relational queries with multi-way joins and aggregations that have been considered notoriously expensive under MPC. To do so, Orq eliminates the quadratic cost of secure joins by leveraging the fact that, in practice, the structure of many real queries allows us to join records and apply the aggregations "on the fly" while keeping the result size bounded. On the system side, Orq contributes generic oblivious operators, a data-parallel vectorized query engine, a communication layer that amortizes MPC network costs, and a dataflow API for expressing relational analytics—all built from the ground up. We evaluate Orq in LAN and WAN deployments on a diverse set of workloads, including complex queries with multiple joins and custom aggregations. When compared to state-of-the-art solutions, Orq significantly reduces MPC execution times and can process one order of magnitude larger datasets. For our most challenging workload, the full TPC-H benchmark, we report results entirely under MPC with Scale Factor 10—a scale that had previously been achieved only with information leakage or the use of trusted compute.

---

## [TRIP: Coercion-resistant Registration for E-Voting with Verifiability and Usability in Votegral](https://dl.acm.org/doi/10.1145/3731569.3764837)

**DOI:** `10.1145/3731569.3764837`

**Authors:**

- Louis-Henri Merino (*EPFL*)
- Simone Colombo (*King's College London*)
- Rene Reyes (*Boston University*)
- Alaleh Azhir (*Harvard University*)
- Shailesh Mishra (*EPFL*)
- Pasindu Tennage (*EPFL*)
- Mohammad Amin Raeisi (*Yale University*)
- Haoqian Zhang (*EPFL*)
- Jeff R. Allen (*EPFL*)
- Bernhard Tellenbach (*Armasuisse*)
- Vero Estrada-Galiñanes (*EPFL*)
- Bryan Ford (*EPFL*)

**Abstract:**

> Online voting is convenient and flexible, but amplifies the risks of voter coercion and vote buying. One promising mitigation strategy enables voters to give a coercer fake voting credentials, which silently cast votes that do not count. Current systems along these lines make problematic assumptions about credential issuance, however, such as strong trust in a registrar and/or in voter-controlled hardware, or expecting voters to interact with multiple registrars. Votegral is the first coercion-resistant voting architecture that leverages the physical security of in-person registration to address these credential-issuance challenges, amortizing the convenience costs of in-person registration by reusing credentials across successive elections. Votegral's registration component, TRIP, gives voters a kiosk in a privacy booth with which to print real and fake credentials on paper, eliminating dependence on trusted hardware in credential issuance. The voter learns and can verify in the privacy booth which credential is real, but real and fake credentials thereafter appear indistinguishable to others. Only voters actually under coercion, a hopefully-rare case, need to trust the kiosk. To achieve verifiability, each paper credential encodes an interactive zero-knowledge proof, which is sound in real credentials but unsound in fake credentials. Voters observe the difference in the order of printing steps, but need not understand the technical details. Experimental results with our prototype suggest that Votegral is practical and sufficiently scalable for real-world elections. User-visible latency of credential issuance in TRIP is at most 19.7 seconds even on resource-constrained kiosk hardware, making it suitable for registration at remote locations or on battery power. A companion usability study indicates that TRIP's usability is competitive with other e-voting systems including some lacking coercion resistance, and formal proofs support TRIP's combination of coercion-resistance and verifiability.

---

## [Moirai: Optimizing Placement of Data and Compute in Hybrid Clouds](https://dl.acm.org/doi/10.1145/3731569.3764802)

**DOI:** `10.1145/3731569.3764802`

**Authors:**

- Ziyue Qiu (*Carnegie Mellon University*)
- Hojin Park (*Carnegie Mellon University*)
- Jing Zhao (*Uber*)
- Yu-Kai Wang (*Uber*)
- Arnav Balyan (*Uber*)
- Gurmeet Singh (*Uber*)
- Yangjun Zhang (*Uber*)
- Suqiang (Jack) Song (*Uber*)
- Gregory R. Ganger (*Carnegie Mellon University*)
- George Amvrosiadis (*Carnegie Mellon University*)

**Abstract:**

> The deployment of large-scale data analytics between on-premise and cloud sites, i.e., hybrid clouds, requires careful partitioning of both data and computation to avoid massive networking costs. We present Moirai, a cost-optimization framework that analyzes job accesses and data dependencies and optimizes the placement of both in hybrid clouds. Moirai informs the job scheduler of data location and access predictions, so it can determine where jobs should be executed to minimize data transfer costs. Our optimizer achieves scalability and cost efficiency by exploiting recurring jobs to identify data dependencies and job access characteristics and reduces the search space by excluding data not accessed recently. We validate Moirai using 4-month traces that span 66.7M queries accessing 13.3EB from Presto and Spark clusters deployed at Uber, a multi-national transportation company leveraging large-scale data analytics for its operations. Moirai reduces hybrid cloud deployment costs by over 97% relative to the state-of-the-art partitioning approach from Alibaba and other public approaches. The savings come from 95–99.5% reduction in cloud egress, up to 99% reduction in replication, and 89–98% reduction in on-premises network infrastructure requirements. We also describe concrete steps being taken towards deploying Moirai in production.

---

## [Tai Chi: A General High-Efficiency Scheduling Framework for SmartNICs in Hyperscale Clouds](https://dl.acm.org/doi/10.1145/3731569.3764851)

**DOI:** `10.1145/3731569.3764851`

**Authors:**

- Bang Di (*Alibaba Cloud*)
- Yun Xu (*Alibaba Cloud*)
- Kaijie Guo (*Alibaba Cloud*)
- Yibin Shen (*Alibaba Cloud*)
- Yu Li (*Alibaba Cloud*)
- Sanchuan Cheng (*Alibaba Cloud*)
- Hao Zheng (*Alibaba Cloud*)
- Fudong Qiu (*Alibaba Cloud*)
- Xiaokang Hu (*Alibaba Group*)
- Naixuan Guan (*Alibaba Cloud*)
- Dongdong Huang (*Alibaba Cloud*)
- Jinhu Li (*Alibaba Cloud*)
- Yi Wang (*Alibaba Cloud*)
- Yifang Yang (*Alibaba Cloud*)
- Jintao Li (*Alibaba Cloud*)
- Hang Yang (*Alibaba Cloud*)
- Chen Liang (*Alibaba Cloud*)
- Yilong Lv (*Alibaba Group*)
- Zikang Chen (*Alibaba Group*)
- Zhenwei Lu (*Alibaba Group*)
- Xiaohan Ma (*Alibaba Group*)
- Jiesheng Wu (*Alibaba Group*)

**Abstract:**

> Cloud service providers increasingly adopt SmartNICs to offload data-plane services (e.g., DPDK and SPDK) and control-plane tasks (such as disk and NIC initialization). Our analysis of production environments reveals that data-plane services statically provision CPUs for peak load, resulting in 67.5% idle CPU cycles during 99% of their runtime in IaaS clouds, leading to wasted CPU resources. On the other hand, control-plane tasks fail to meet critical Service Level Objectives (SLOs), such as virtual machine startup time. Unfortunately, achieving control-plane SLO improvements through co-scheduling with idle data-plane services remains highly challenging, due to the combined effects of intrinsic scheduling latency and the substantial architectural complexity inherent to control-plane ecosystems. We present Tai Chi, a hardware and software co-designed scheduler that coordinates control-plane tasks and dataplane services through a SmartNIC-accelerated hybrid virtualization. This hybrid framework unifes physical and virtual CPUs within a single OS while providing native inter-process communication semantics among all tasks. By achieving microsecond-scale scheduling precision, it reduces control-plane operation latency by 3.1× (e.g., VM startup) while maintaining data-plane SLO compliance, imposes negligible scheduling overhead, and requires zero code modifications to legacy control-plane systems. Its cross-platform SmartNIC compatibility enables seamless and transparent deployment in the production environment, demonstrating compelling advantages over prior solutions in hyperscale cloud infrastructure.

---

## [Quilt: Resource-aware Merging of Serverless Workflows](https://dl.acm.org/doi/10.1145/3731569.3764830)

**DOI:** `10.1145/3731569.3764830`

**Authors:**

- Yuxuan Zhang (*University of Pennsylvania*)
- Sebastian Angel (*University of Pennsylvania*)

**Abstract:**

> This paper describes Quilt, a serverless optimizer that automatically merges workflows that consist of many functions (possibly in different languages) into one process thereby avoiding high invocation latency, communication overhead, and long chains of cold starts. Instead of merging all functions, Quilt takes into account the provider's resource constraints to decide which functions to merge. Quilt is compatible with existing platforms without modification (Fission, OpenWhisk, and OpenFaaS), can merge functions in different languages (C, C++, Swift, Go, Rust) by acting at the level of LLVM IR, and requires no input or help from developers. Our evaluation shows that Quilt improves median workflow completion time by 45.63%–70.95% and throughput by 2.05×–12.87×.

---

## [Mantle: Efficient Hierarchical Metadata Management for Cloud Object Storage Services](https://dl.acm.org/doi/10.1145/3731569.3764824)

**DOI:** `10.1145/3731569.3764824`

**Authors:**

- Jiahao Li (University of Science and Technology of China (*University of Science and Technology of China*)
- Baidu (China) Co. (*University of Science and Technology of China*)
-  Ltd) (*University of Science and Technology of China*)
- Biao Cao (*University of Science and Technology of China*)
- Jielong Jian (Baidu (China) Co. (*University of Science and Technology of China*)
-  Ltd) (*University of Science and Technology of China*)
- Cheng Li (The University of Science and Technology of China (*University of Science and Technology of China*)
- Institute of Artificial Intelligence (*University of Science and Technology of China*)
- Hefei Comprehensive National Science Center) (*University of Science and Technology of China*)
- Sen Han (*University of Science and Technology of China*)
- Yiduo Wang (*University of Science and Technology of China*)
- Yufei Wu (*University of Science and Technology of China*)
- Kang Chen (*Tsinghua University*)
- Zhihui Yin (*Tsinghua University*)
- Qiushi Chen (*Tsinghua University*)
- Jiwei Xiong (*Tsinghua University*)
- Jie Zhao (*Tsinghua University*)
- Fengyuan Liu (*Tsinghua University*)
- Yan Xing (*Tsinghua University*)
- Liguo Duan (*Tsinghua University*)
- Miao Yu (*Tsinghua University*)
- Ran Zheng (Baidu (China) Co. (*Tsinghua University*)
-  Ltd) (*Tsinghua University*)
- Feng Wu (University of Science and Technology of China (*Tsinghua University*)
- Institute of Artificial Intelligence (*Tsinghua University*)
- Hefei Comprehensive National Science Center) (*Tsinghua University*)
- Xianjun Meng (Baidu (China) Co. (*Tsinghua University*)
-  Ltd) (*Tsinghua University*)

**Abstract:**

> Cloud Object Storage Services (COSSs) are the primary storage backend in the cloud, supporting large-scale analytics and ML workloads that frequently access deep object paths and update metadata concurrently. However, current COSS architectures incur costly multi-round lookups and high directory contention, delaying job execution. Prior optimizations, largely designed for distributed file systems (with least adoption in clouds), do not apply due to COSS-specific constraints like stateless proxies and limited APIs. Mantle is a new COSS metadata service for modern cloud workloads. It adopts a two-layer architecture: a scalable, sharded database (TafDB) shared across namespaces and a per-namespace, single-server IndexNode consolidating lightweight directory metadata. With a fine-grained division of metadata and responsibility, Mantle supports up to 10 billion objects or directories in a single namespace and achieves 1.8 million lookups per second through scalable execution of single-RPC lookups on IndexNode. It also delivers up to 58K directory updates per second under high contention by integrating out-of-place delta updates in TafDB and offloading loop detection for cross-directory renames to IndexNode, both effectively eliminating coordination bottlenecks. Compared to the metadata services of Tectonic, InfiniFS and LocoFS, Mantle reduces metadata latency by 6.6-99.1% and improves throughput by 0.07-115.00×. With data access enabled, it shortens job completion times by 63.3–93.3% for interactive Spark analytics and 38.5–47.7% for AI-driven audio preprocessing tasks. Mantle has been deployed on Baidu Object Storage (BOS) for over 2 years, a service offered by Baidu Canghai Storage.

---

## [Unlocking True Elasticity for the Cloud-Native Era with Dandelion](https://dl.acm.org/doi/10.1145/3731569.3764803)

**DOI:** `10.1145/3731569.3764803`

**Authors:**

- Tom Kuchler (*ETH Zurich*)
- Pinghe Li (*ETH Zurich*)
- Yazhuo Zhang (*ETH Zurich*)
- Lazar Cvetković (*ETH Zurich*)
- Boris Goranov (*ETH Zurich*)
- Tobias Stocker (*ETH Zurich*)
- Leon Thomm (*ETH Zurich*)
- Simone Kalbermatter (*ETH Zurich*)
- Tim Notter (*ETH Zurich*)
- Andrea Lattuada (*MPI-SWS*)
- Ana Klimovic (*ETH Zurich*)

**Abstract:**

> Elasticity is fundamental to cloud computing. An elastic platform can quickly allocate resources to match the demand of each workload as it arrives, rather than pre-provisioning resources to meet performance objectives. However, even serverless platforms — which boot sandboxes in 10s to 100s of milliseconds — are not sufficiently elastic to avoid pre-provisioning expensive resources. Today's FaaS platforms provision many extra, idle sandboxes in memory to reduce the occurrence of slow, cold starts. Initializing securely isolated sandboxes with a POSIX-like computing environment that today's cloud users expect is slow as it requires booting a guest OS and configuring networking. Our key insight is that the rise of cloud-native application development provides an opportunity to rethink the application interface to the cloud and co-design a much more efficient, elastic computing platform under the hood. We propose Dandelion, an elastic cloud platform with a declarative cloud-native programming model that replaces POSIX-based network interfaces with higher-level (e.g., HTTP-based) interfaces for applications to interact with remote services like cloud storage, databases, and AI inference services. Dandelion executes applications expressed as DAGs of pure compute functions and communication functions. This enables Dandelion to securely execute compute functions in lightweight sandboxes that cold start in 100s of microseconds, since pure functions do not rely on software environments such as a guest OS. Dandelion makes it practical to boot sandboxes on-demand per request, decreasing performance variability by two to three orders of magnitude compared to Firecracker and reducing committed memory by 96% on average when running the Azure Functions trace.

---

## [Running Consistent Applications Closer to Users with Radical for Lower Latency](https://dl.acm.org/doi/10.1145/3731569.3764831)

**DOI:** `10.1145/3731569.3764831`

**Authors:**

- Nicolaas Kaashoek (*Princeton University*)
- Oleg A. Golev (*Sentient Foundation*)
- Austin T. Li (*Cornell University*)
- Amit Levy (*Cornell University*)
- Wyatt Lloyd (Princeton University). (*Cornell University*)

**Abstract:**

> Running applications close to users—in nearby datacenters, at edge points of presence, or in on-premises clusters—is attractive, as it reduces end-to-end latency. Moving strong consistent applications closer to users is difficult, as they incur high latencies either when accessing, or coordinating, their storage system. This restricts such applications to running co-located with their data, in a datacenter. Radical allows these applications to leverage the latency benefits that come from running near users. Radical uses its new LVI protocol to perform all necessary coordination in a single request. This request guarantees linearizability with a combination of locks, a validation step, and write intents. Radical hides the latency of the LVI request by overlapping it with speculative execution of the application. Our evaluation shows that Radical achieves 84–89% of the latency improvement obtainable by moving out of the datacenter, while providing Linearizability.

---

## [Managing Scalable Direct Storage Accesses for GPUs with GoFS](https://dl.acm.org/doi/10.1145/3731569.3764857)

**DOI:** `10.1145/3731569.3764857`

**Authors:**

- Shaobo Li (*University of Illinois Urbana-Champaign*)
- Yirui Eric Zhou (*University of Illinois Urbana-Champaign*)
- Yuqi Xue (*University of Illinois Urbana-Champaign*)
- Yuan Xu (*University of Illinois Urbana-Champaign*)
- Jian Huang (*University of Illinois Urbana-Champaign*)

**Abstract:**

> As we shift from CPU-centric computing to GPU-accelerated computing for supporting intelligent data processing at scale, the storage bottleneck has been exacerbated. To bypass the host CPUand alleviate unnecessary data movements, modern GPUs enable direct storage access to SSDs (i.e., GPUDirect Storage). However, current GPUDirect Storage solutions still rely on the host file system to manage the storage device, direct storage accesses are still bottlenecked by the host. In this paper, we develop a GPU-orchestrated file system (GoFS) for scaling the direct storage accesses for GPU programs, by fully offloading the storage management to the GPU. As GoFS provides POSIX API and manages core filesystem structures in GPU memory, it can execute both control path and data path without host CPU involvement. To enable highly concurrent direct storage accesses, we rethink the design and implementation of core filesystem structures with various optimization techniques, such as scalable data indexing, fine-grained per-SM (streaming multiprocessor) block management, and zero-copy I/O accesses, by carefully exploring the GPU-accelerated computing paradigm. GoFS preserves the essential filesystem properties such as crash consistency, and it is compatible with existing host-based file systems like F2FS. GoFS does not require changes to the on-disk filesystem organization, therefore, the host and GPU can manage the SSD in a coordinated fashion, and maintain the data consistency in a primary/secondary mode. We implement GoFS based on F2FS using 7.9K lines of codes with CUDA programming. We examine its efficiency on an A100 GPU. Our experiments with various GPU-based applications show that GoFS outperforms state-of-the-art storage access solutions for GPUs by 1.61× on average.

---

## [PhoenixOS: Concurrent OS-level GPU Checkpoint and Restore with Validated Speculation](https://dl.acm.org/doi/10.1145/3731569.3764813)

**DOI:** `10.1145/3731569.3764813`

**Authors:**

- Xingda Wei (*Institute of Parallel and Distributed Systems, Shanghai Jiao Tong University*)
- Zhuobin Huang (*National University of Singapore*)
- Tianle Sun (*Institute of Parallel and Distributed Systems, Shanghai Jiao Tong University*)
- Yingyi Hao (*Institute of Parallel and Distributed Systems, Shanghai Jiao Tong University*)
- Rong Chen (*Institute of Parallel and Distributed Systems, Shanghai Jiao Tong University*)
- Mingcong Han (*Institute of Parallel and Distributed Systems, Shanghai Jiao Tong University*)
- Jinyu Gu (*Institute of Parallel and Distributed Systems, Shanghai Jiao Tong University*)
- Haibo Chen (*Institute of Parallel and Distributed Systems, Shanghai Jiao Tong University*)

**Abstract:**

> 

---

## [KTransformers: Unleashing the Full Potential of CPU/GPU Hybrid Inference for MoE Models](https://dl.acm.org/doi/10.1145/3731569.3764843)

**DOI:** `10.1145/3731569.3764843`

**Authors:**

- Hongtao Chen (*Tsinghua University*)
- Weiyu Xie (*Tsinghua University*)
- Boxin Zhang (*Tsinghua University*)
- Jingqi Tang (*Approaching.AI*)
- Jiahao Wang (*Approaching.Al, Hangzhou Dianzi University*)
- Jianwei Dong (*Tsinghua University*)
- Shaoyuan Chen (*Tsinghua University*)
- Ziwei Yuan (*Approaching.AI, University of Electronic Science and Technology of China*)
- Chen Lin (*Tsinghua University*)
- Chengyu Qiu (*Tsinghua University*)
- Yuening Zhu (*Tsinghua University*)
- Qingliang Ou (*Approaching.AI, Beijing University of Posts and Telecommunications*)
- Jiaqi Liao (*Approaching.AI, Beijing Institute of Technology*)
- Xianglin Chen (*Approaching.AI*)
- Zhiyuan Ai (*Approaching.AI*)
- Yongwei Wu (*Tsinghua University*)
- Mingxing Zhang (*Tsinghua University*)

**Abstract:**

> Due to the sparse nature of Mixture-of-Experts (MoE) models, they are particularly suitable for hybrid CPU/GPU inference, especially in low-concurrency scenarios. This hybrid approach leverages both the large, cost-effective memory capacity of CPU/DRAM and the high bandwidth of GPU/VRAM. However, existing hybrid solutions remain bottlenecked by CPU computation limits and CPU-GPU synchronization overheads, severely restricting their ability to efficiently run state-of-the-art large MoE models, such as the 671B DeepSeek-V3/R1. This paper presents KTransformers, a high-performance inference system designed specifically for efficient heterogeneous computing of diverse MoE models. KTransformers employs optimized, AMX-specialized kernels that fully utilize the computational capabilities of modern CPUs and incorporates an asynchronous CPU-GPU task scheduling mechanism to minimize overhead—achieving 4.62–19.74× prefilling speedups and 1.25–4.09× decoding speedups compared to existing systems. Furthermore, we propose a novel Expert Deferral mechanism that strategically enhances the potential for overlapping CPU and GPU computations, increasing CPU utilization from typically below 75% to almost 100%. This yields up to 1.45× additional throughput beyond the aforementioned optimizations, with an average model accuracy drop of no more than 0.5% across a diverse set of benchmarks. The resulting system, KTransformers, substantially enhances the accessibility of large MoE models for local users who prioritize security or intend to dig into the internals of the models. As a result, it has already been widely adopted within both the open-source community and industry.

---

## [Aegaeon: Effective GPU Pooling for Concurrent LLM Serving on the Market](https://dl.acm.org/doi/10.1145/3731569.3764815)

**DOI:** `10.1145/3731569.3764815`

**Authors:**

- Yuxing Xiang (*Peking University*)
- Xue Li (*Alibaba Group*)
- Kun Qian (*Alibaba Group*)
- Yufan Yang (*Alibaba Group*)
- Diwen Zhu (*Alibaba Group*)
- Wenyuan Yu (*Alibaba Group*)
- Ennan Zhai (*Alibaba Group*)
- Xuanzhe Liu (*Peking University*)
- Xin Jin (*Peking University*)
- Jingren Zhou (*Alibaba Group*)

**Abstract:**

> Model markets (e.g., Hugging Face) feature a wide variety of models with unique characteristics and varying levels of popularity. Serving sporadic and unpredictable requests in concurrent inference workloads with dedicated GPU instances results in substantial resource waste. While existing multi-model serving solutions use GPU pooling and server-less computing to improve resource efficiency, their effective-ness is limited to supporting at most two or three models per GPU, which is inadequate for fully utilizing GPU resources. We propose Aegaeon, a multi-model serving system that performs model auto-scaling at the token granularity to achieve effective GPU pooling. Aegaeon schedules multimodel requests and makes auto-scaling decisions on a per-token basis to maximize service quality. It reduces auto-scaling overhead by 97% through component reuse, explicit memory management, and fine-grained KV cache synchronization. Experiments show that Aegaeon sustains 2–2.5× higher request arrival rates or 1.5–9× more goodput compared to existing solutions. Aegaeon has been beta deployed in our model marketplace and currently serves tens of models. Deployment results show that Aegaeon reduces the number of GPUs required for serving these models from 1,192 to 213, highlighting an 82% GPU resource saving.

---

## [Mercury: Unlocking Multi-GPU Operator Optimization for LLMs via Remote Memory Scheduling](https://dl.acm.org/doi/10.1145/3731569.3764798)

**DOI:** `10.1145/3731569.3764798`

**Authors:**

- Yue Guan (*UCSD*)
- Xinwei Qiang (*UCSD*)
- Zaifeng Pan (*UCSD*)
- Daniels Johnson (*Meta*)
- Yuanwei Fang (*Meta*)
- Keren Zhou (*George Mason University, OpenAI*)
- Yuke Wang (*Rice University*)
- Wanlu Li (*UCSD*)
- Yufei Ding (*UCSD, Meta*)
- Adnan Aziz (*Meta*)

**Abstract:**

> In this paper, we propose Mercury, a multi-GPU operator compiler based on a loop-based intermediate representation, CommIR. At the core of Mercury is an abstraction that treats remote GPU memory as an explicitly managed extension of the memory hierarchy, expanding the available storage and communication resources beyond local HBM. This unified view enables the compiler to reason holistically about data placement and inter-device communication, unlocking a vastly larger design space that encompasses and extends beyond existing manual strategies. As a result, Mercury is able to automatically reproduce the performance of hand-optimized baselines like RingAttention and Ulysses, and in some configurations, even discovers more effective strategies that manual designs have overlooked. Our implementation is open-sourced at https://github.com/ChandlerGuan/mercury_artifact.

---

## [How to Copy Memory? Coordinated Asynchronous Copy as a First-Class OS Service](https://dl.acm.org/doi/10.1145/3731569.3764800)

**DOI:** `10.1145/3731569.3764800`

**Authors:**

- Jingkai He (*Shanghai Jiao Tong University*)
- Yunpeng Dong (*Shanghai Jiao Tong University*)
- Dong Du (*Shanghai Jiao Tong University*)
- Mo Zou (*Huawei Technologies*)
- Zhitai Yu (*Huawei Technologies*)
- Yuxin Ren (*Huawei Technologies*)
- Ning Jia (*Huawei Technologies*)
- Yubin Xia (*Shanghai Jiao Tong University*)
- Haibo Chen (*Shanghai Jiao Tong University*)

**Abstract:**

> In modern systems, memory copy remains a critical performance bottleneck across various scenarios, playing a pervasive role in system-wide execution such as syscalls, IPC, and user-mode applications. Numerous efforts have aimed at optimizing copy performance, including zero-copy with page remapping and hardware-accelerated copy. However, they typically target specific use cases, such as Linux zero-copy send() for messages of ≥10KB. This paper argues for copy as a first-class OS service, offering three key benefits: (1) with the asynchronous copy abstraction provided by the service, applications can overlap their execution with copy; (2) the service can effectively utilize hardware capabilities to enhance copy performance; (3) the service's global view of copies further enables holistic optimization. To this end, we introduce Copier, a new OS service of coordinated asynchronous copy, to serve both user-mode applications and OS services. We build Copier-Linux to demonstrate Copier's ability to improve performance for diverse use cases, including Redis, Protobuf, network stack, proxy, etc. Evaluations show that Copier achieves up to a 1.8 × speedup for real-world applications like Redis and a 1.6 × improvement over zIO, the state-of-the-art in optimizing copy efficiency. To further facilitate adoption, we develop a toolchain to ease the use of Copier. We also integrate Copier into a commercial smartphone OS (HarmonyOS 5.0), achieving promising results.

---

## [CortenMM: Efficient Memory Management with Strong Correctness Guarantees](https://dl.acm.org/doi/10.1145/3731569.3764836)

**DOI:** `10.1145/3731569.3764836`

**Authors:**

- Junyang Zhang (*Peking University and Zhongguancun Laboratory*)
- Xiangcan Xu (*Peking University*)
- Yonghao Zou (*Peking University*)
- Zhe Tang (*Peking University and Zhongguancun Laboratory*)
- Xinyi Wan (*Ant Group*)
- Kang Hu (*Peking University and Zhongguancun Laboratory*)
- Siyuan Wang (*Peking University and Zhongguancun Laboratory*)
- Wenbo Xu (*Peking University and Zhongguancun Laboratory*)
- Di Wang (*Peking University and Zhongguancun Laboratory*)
- Hao Chen (*CertiK*)
- Lin Huang (*Ant Group*)
- Shoumeng Yan (*Ant Group*)
- Yuval Tamir (*UCLA*)
- Yingwei Luo (*Peking University and Zhongguancun Laboratory*)
- Xiaolin Wang (*Peking University and Zhongguancun Laboratory*)
- Huashan Yu (*Peking University and Zhongguancun Laboratory*)
- Zhenlin Wang (*Michigan Tech*)
- Hongliang Tian (*Ant Group*)
- Diyu Zhou (*Peking University*)

**Abstract:**

> Modern memory management systems suffer from poor performance and subtle concurrency bugs, slowing down applications while introducing security vulnerabilities. We observe that both issues stem from the conventional design of memory management systems with two levels of abstraction: a software-level abstraction (e.g., VMA trees in Linux) and a hardware-level abstraction (typically, page tables). This design increases portability but requires correctly and efficiently synchronizing two drastically different and complex data structures, which is generally challenging. We present CortenMM, a memory management system with a clean-slate design to achieve both high performance and synchronization correctness. Our key insight is that most OSes no longer need the software-level abstraction, since mainstream ISAs use nearly identical hardware MMU formats. Therefore, departing from prior designs, CortenMM eliminates the software-level abstraction to achieve sweeping simplicity. Exploiting this simplicity, CortenMM proposes a transactional interface with scalable locking protocols to program the MMU, achieving high performance by avoiding the extra contention in the software-level abstraction. The one-level design further enables us to formally verify the correctness of concurrent code operating on the MMU (correctness of basic operations and locking protocols), thereby offering strong correctness guarantees. Our evaluation shows that the formally verified CortenMM outperforms Linux by 1.2× to 26× on real-world applications.

---

## [Rearchitecting the Thread Model of In-Memory Key-Value Stores with μTPS](https://dl.acm.org/doi/10.1145/3731569.3764794)

**DOI:** `10.1145/3731569.3764794`

**Authors:**

- Youmin Chen (*Shanghai Jiao Tong University*)
- Jiwu Shu (*Tsinghua University*)
- Yanyan Shen (*Shanghai Jiao Tong University*)
- Linpeng Huang (*Shanghai Jiao Tong University*)
- Hong Mei (*Shanghai Jiao Tong University*)

**Abstract:**

> This paper presents μTPS, a new thread architecture tailored for in-memory key-value stores (KVSs) that operate at tens of millions of operations per second. We show through analysis and demonstration that the widely used run-to-completion thread architecture, which executes monolithic functions from start to finish, often suffers from cache inefficiencies and contention issues. To address this, we revisit the once widely used thread-per-stage (TPS) architecture, but with a fresh perspective – separating cache-resident, contention-free stages and memory-resident, conflict-prone stages into distinct thread pools, and scheduling them with dedicated hardware resources (e.g., CPU cores, cache ways). This novel division enables independent optimization of each stage, significantly improving cache efficiency and mitigating contention. Additionally, μTPS incorporates reconfigurable RPC, resizable caching, and an auto-tuner to enhance its schedulability and performance. We implement two in-memory key-value stores, μTPS-H and μTPS-T, to demonstrate the effectiveness of this approach. Evaluation results show that μTPS achieves higher performance than the run-to-completion counterparts.

---

## [FlexGuard: Fast Mutual Exclusion Independent of Subscription](https://dl.acm.org/doi/10.1145/3731569.3764852)

**DOI:** `10.1145/3731569.3764852`

**Authors:**

- Victor Laforet (*Inria*)
- Sanidhya Kashyap (*EPFL*)
- Călin Iorgulescu (*Oracle Labs*)
- Julia Lawall (*Inria*)
- Jean-Pierre Lozi (*Inria*)

**Abstract:**

> Performance-oriented applications require efficient locks to harness the computing power of multicore architectures. While fast, spinlock algorithms suffer severe performance degradation when thread counts exceed available hardware capacity, i.e., in oversubscribed scenarios. Existing solutions rely on imprecise heuristics for blocking, leading to suboptimal performance. We present FlexGuard, the first approach that systematically switches from busy-waiting to blocking precisely when a lock-holding thread is preempted. Flex-Guard achieves this by communicating with the OS scheduler via eBPF, unlike prior approaches. FlexGuard matches or improves performance in LevelDB, a memory-optimized database index, PARSEC's Dedup, and SPLASH2X's Raytrace and Streamcluster, boosting throughput by 1–6× in non-oversubscribed and up to 5× in oversubscribed scenarios.

---

## [Scalable Address Spaces using Concurrent Interval Skiplist](https://dl.acm.org/doi/10.1145/3731569.3764807)

**DOI:** `10.1145/3731569.3764807`

**Authors:**

- Tae Woo Kim (*KAIST*)
- Youngjin Kwon (*KAIST*)
- Jeehoon Kang (*KAIST / FuriosaAI*)

**Abstract:**

> A kernel's address space design can significantly bottleneck multi-threaded applications, as address space operations such as mmap() and munmap() are serialized by coarsegrained locks like Linux's mmap_lock. Such locks have long been known as one of the most intractable contention points in memory management. While prior works have attempted to address this issue, they either fail to sufficiently parallelize operations or are impractical for real-world kernels. We present the first scalable and practical address space design that parallelizes critical operations. We identify key scalability bottlenecks—many of which extend beyond address spaces—and address them with targeted solutions. At its core is the concurrent interval skiplist, a new data structure that integrates mapping and locking for parallel interval operations. We implement our design on Linux 6.8 and evaluate it on a dual-socket 48-core machine. Our results show a significant throughput improvement of 13.1× for an mmap() microbenchmark, 4.49× for LevelDB, 3.19× for the Apache web server, 1.47× for Metis MapReduce, and 1.27× for Psearchy text indexing.

---

