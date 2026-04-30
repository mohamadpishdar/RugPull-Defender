
🧠 Rug‑Pull Defender — Repository Overview
This repository provides a complete, research‑grade framework for early detection of rug‑pull scams in blockchain projects. It combines a leakage‑free forensic dataset, static smart‑contract analysis, and a multi‑modal ensemble detection system to enable robust and reproducible research on DeFi security.
Unlike prior work that focuses on a single modality (e.g., transactions only or contract patterns only), this project is designed around the principle that rug‑pull attacks are multi‑dimensional phenomena requiring semantic, structural, and behavioral evidence.

📦 Repository Components
The repository is organized into three main pillars:

📊 Dataset (dataset/)
This directory contains the TM‑RugPull dataset, a carefully curated and leakage‑free benchmark designed for early‑stage rug‑pull detection.
Key characteristics:

1000 labeled token projects across multiple categories:

DeFi protocols
Meme coins
NFTs
Celebrity‑themed and experimental tokens


Temporal hygiene: all features are extracted strictly from the first half of each project’s lifecycle, preventing any form of post‑hoc data leakage.
Expert‑validated labels, based on forensic evidence of liquidity withdrawal, abandonment, and long‑term inactivity.

The dataset provides multimodal features across:

On‑chain activity (transactions, liquidity events)
Smart‑contract metadata (structure and permissions)
OSINT indicators (social media footprint and reputation signals)

This makes the dataset suitable for causal and early‑warning detection models, rather than retrospective classification.

🔎 Static Analysis (static_analysis/)
This directory contains a reproducible static smart‑contract analysis pipeline, centered around CRPWarner and bytecode‑level reasoning.
Core capabilities include:

Extraction of runtime bytecode (from on‑chain sources or compilation)
Static analysis using CRPWarner + Gigahorse + Soufflé
Batch execution and benchmarking against expert‑labeled ground truth

The workflow is designed to support:

Research replication
Detector benchmarking
Extension to future static analyzers

All scripts required for compilation, bytecode retrieval, CRPWarner execution, and result comparison are provided.

🤖 Ensemble Detector (ensemble_detector/)
This directory contains the core implementation of Rug‑Pull Defender, a multi‑modal ensemble detection system.
The detection pipeline integrates three complementary views of risk:


Semantic Analysis (CodeBERT)
Transformer‑based embeddings capture the intent and logic of smart contracts, enabling robustness against semantic obfuscation and misleading identifiers.


Knowledge‑Driven Heuristics (Forta‑Inspired Rules)
Lightweight rule‑based analysis detects known rug‑pull patterns (e.g., minting, owner‑only withdrawals, blacklist manipulation).


Structural Analysis (CRP‑Warner Features)
Bytecode‑level indicators highlight hidden minting, liquidity leakage, and sell restrictions.


These signals are fused using a LightGBM ensemble classifier, producing a robust and well‑calibrated prediction suitable for both experimental evaluation and deployment‑oriented scenarios (e.g., real‑time mempool screening).






