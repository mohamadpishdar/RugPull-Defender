# Rug‑Pull Defender — Repository Overview

The present repository offers a comprehensive, research-ready solution for detecting rug-pull scams in blockchain projects by incorporating an airtight forensic data set, static code analysis of smart contracts, and multimodal ensemble scam detection methods for conducting reliable research on DeFi security.

In contrast to existing research that relies on only one modality (such as just transactions or patterns from contracts), this project was developed based on the idea that rug-pulls represent multidimensional events.

## Repository Components

Three major pillars constitute the repository:

## Dataset (dataset/)

This directory includes the TM-RugPull dataset, which is carefully designed and is leakage-free to test early-stage rug-pull detection algorithms.

### Key Characteristics

1000 tokenized projects, belonging to various categories:
- DeFi protocols
- Meme coins
- NFTs
- Celebrity‑themed and experimental tokens

### Temporal hygiene

All features were extracted using solely the first half of each project’s lifecycle and thereby precluding any post-hoc data leakage.

### Expert‑validated labels

The labels were acquired based on forensic signs of liquidity drain, abandonment, and extended inactivity periods.

### Multimodal Features

The dataset provides features across three complementary layers:

- On‑chain activity (transactions, liquidity events)
- Smart‑contract metadata (structure and permissions)
- OSINT indicators (social media footprint and reputation signals)

The design is conducive to building causal and early warning detection systems, but not classifiers.

## Static Analysis (static_analysis/)

This directory provides a reproducible pipeline for analyzing static smart contract code, with an emphasis on using CRPWarner and bytecode-level logic.

### Core Capabilities

- Runtime bytecode extraction (from on‑chain sources or local compilation)
- Static analysis using CRPWarner + Gigahorse + Soufflé
- Batch execution and benchmarking against expert‑labeled ground truth

### Design Goals

The workflow is designed to support:

- Research replication
- Detector benchmarking
- Extension to future static analyzers

All scripts required to compile contracts, retrieve their bytecode, analyze them using CRPWarner, and compare results are provided.

## Ensemble Detector (ensemble_detector/)

This directory provides the core implementation of Rug-Pull Defender, which builds a multi-modal ensemble detector for rug pulls from different risk signals.

## Detection Modalities

The detection pipeline combines three complementary perspectives:

### Semantic Analysis (CodeBERT)

Transform-based embeddings encode the meaning and semantics of smart contracts, allowing resilience against any semantic misrepresentation and confusing naming conventions.

### Knowledge-Based Heuristics (Forta-Supported Rules)

Lightweight rule‑based analysis detects well‑known rug‑pull patterns such as:

- Minting privileges
- Owner‑only withdrawals
- Blacklist and fee manipulation

### Structural Analysis (CRP‑Warner Features)

Bytecode‑level indicators reveal:

- Hidden minting behavior
- Liquidity leakage paths
- Sell‑restriction mechanisms

## Ensemble Fusion

Fusion of all signals is done via a LightGBM ensemble classifier, producing well-calibrated and robust prediction models appropriate for:

- Experimental evaluation
- Deployment‑oriented settings (e.g., real‑time mempool screening)
