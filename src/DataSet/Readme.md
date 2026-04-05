
📝 Overview

This Dataset is a carefully crafted leakage-free Dataset, intended to detect Rug-Pull scams at their nascent stages. While current Datasets only focus on DeFi projects, the TM-RugPull dataset includes an eclectic mix of projects ranging from Meme Coins, NFTs, and celebrity-themed Tokens.

The most notable feature of this Dataset is its Temporal Hygiene, which guarantees that all attributes are selected exclusively from the initial half of the project’s life cycle, thereby preventing “data leakage.

📊 Dataset Statistics

Number of total projects: 1000 token projects.

Project Scope: Multiverse (Decentralized finance applications, NFTs, meme tokens, et al.)

Labelling: Based on forensic findings and criteria of longevity, with validation through a consensus of multiple experts.

🏗️ Multimodal Features

The dataset offers features within three main layers as follows:

On-chain activity: Transactions and liquidity pooling.

Smart contract metadata: Structure and semantics of the code.

OSINT signals: Social media footprint and reputation-related indicators.

🛡️ Key Features

Leakage Proof: All features are timestamp-tested to confirm their existence prior to the scam event.

Evidence-Based: Built on solving the problems of "ambiguous labeling" and "limited modality" present in existing blockchain security studies.

Causal Evidence: Makes possible the creation of effective early detection systems despite limited data availability.

features/: Multimodal feature vectors have been extracted.

labels/: Labels (rug-pull vs. legitimate) with annotations from experts.


