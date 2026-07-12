# TM-RUGPULL DataSet

This is a well-crafted leakage-free Dataset aimed at spotting rug-pull frauds in their early stages. In contrast to other datasets where only DeFi projects have been considered, the TM-RugPull Dataset contains a mixture of projects comprising meme coins, NFTs, and even tokens associated with celebrities.

One of the major characteristics of this Dataset is temporal hygiene, which ensures that all the attributes chosen are drawn strictly during the first half of the project's life cycle to avoid data leakage.

## Dataset Statistics

Total number of projects: 1000 token projects.

Scope of Project: Multiverse (Decentralized finance, NFTs, meme coins, etc.)

Labeling: According to forensic evidence and longevity criteria, validated via the consensus of several experts.

## Multimodal Features

The data contains the following features across three layers:

- On-chain layer: Transaction activity and liquidity pools.
- Smart contract layer: Code structure and semantic information.
- OSINT layer: Social media presence and reputation.

## Key Features

Proof of Leakage: All features are time-stamped to ensure that they existed before the scam took place.

Evidence-Based Approach: Based on addressing the issues of "ambiguity of labeling" and "modality limitation" in previous research on blockchain security.

Evidence of Causality: Enables the development of efficient early detection systems despite a lack of sufficient data.

## Citation: 
Shoaei, F., Pishdar, M., Bag-Mohammadi, M., Karami, M., & Lagaisse, B. (2026). TMRugPull: A Temporally Sound Multimodal Dataset for Early RugPull Detection. arXiv preprint arXiv:2602.21529.

## Data Structure

features/: Feature vectors in multimodal form have been obtained.

labels/: Label (whether rug-pull or legitimate) annotated by experts.

