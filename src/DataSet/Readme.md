
📝 Overview

TM-RugPull is a rigorously curated, leakage-resistant dataset designed for the early detection of Rug-Pull scams. Unlike existing datasets that focus solely on DeFi, TM-RugPull covers a diverse range of tokenized projects including Meme coins, NFTs, and Celebrity-themed tokens.

The core strength of this dataset is its Temporal Hygiene, ensuring that all features are extracted strictly from the first half of each project's lifespan to avoid "data leakage" and ensure the model learns to predict scams before they occur.

📊 Dataset Statistics

Total Projects: 1000 token projects.

Scope: Multi-ecosystem (DeFi, NFTs, Meme coins, etc.).

Labeling: Grounded in forensic reports and longevity criteria, verified through multi-expert consensus.

🏗️ Multimodal Features

The dataset provides features across three primary layers:

On-chain Behavior: Transactional data and liquidity pool dynamics.

Smart Contract Metadata: Structural and semantic information from the contract code.

OSINT Signals: Social media presence and off-chain reputation indicators.

🛡️ Key Features

Leakage-Resistant: All features are timestamp-checked to ensure they precede the scam event.

Scientifically Grounded: Designed to solve the "ambiguous labeling" and "narrow modality" issues in current blockchain security research.

Causally Valid: Enables the development of early-warning systems that are effective in real-world, data-scarce environments.

features/: Extracted multimodal feature vectors.

labels/: Binary labels (Rug-pull vs. Legitimate) with expert verification notes.


