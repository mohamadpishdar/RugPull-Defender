
This Python script implements an end‑to‑end rug‑pull detection pipeline for smart contracts. The code loads smart contract source code, extracts multiple types of risk signals, and combines them into a single machine‑learning model to predict whether a contract is a rug‑pull scam or benign.
Below is a step‑by‑step explanation of what the script does.

1. Environment Setup and Dependencies
The script first installs and imports all required libraries, including:

PyTorch and Transformers for CodeBERT embeddings
LightGBM for the ensemble classifier
Pandas and NumPy for data processing
Scikit‑learn for PCA, scaling, and evaluation
RAR/ZIP utilities to extract smart contract source files

This ensures the entire pipeline can run inside a single notebook or execution environment (e.g., Google Colab).

2. Input Data Loading
The script expects three main inputs:

An Excel file containing:

Smart contract identifiers
Ground‑truth labels (scam / normal)


A ZIP or RAR archive containing the Solidity source code of the contracts
(Optional) A CRP‑Warner output file containing static risk indicators

All contract identifiers are normalized to strings to ensure consistent matching across files.

3. Source Code Extraction
The compressed archive containing contract source code is extracted into a local folder.
Each contract file is mapped to its identifier using its filename.
If a contract’s source code is missing, the script safely handles it by assigning empty features.

4. Forta‑Inspired Rule‑Based Risk Scoring
The script implements a lightweight simulation of Forta‑style heuristic rules.
For each smart contract, it scans the source code for suspicious patterns such as:

Owner‑only privileges (onlyOwner)
Token minting (mint)
Liquidity withdrawal (withdraw, drain)
Blacklisting or fee manipulation
Low‑level calls and inline assembly

Each pattern contributes a weighted risk score.
The result is a numeric heuristic risk feature, representing knowledge‑based detection signals.

This layer does not replicate Forta itself—it approximates its core rule‑based logic in a reproducible and lightweight way.


5. CodeBERT Semantic Embedding
Each smart contract source code is processed using CodeBERT:

The code is tokenized and truncated to a maximum of 512 tokens
CodeBERT encodes the code using a transformer model
The output token representations are averaged into a single 768‑dimensional embedding vector

This embedding captures the semantic intent of the code, even when names are obfuscated or misleading.
If a contract has no source code, a zero vector is used instead.

6. Dimensionality Reduction (PCA)
Because CodeBERT embeddings are high‑dimensional, the script applies Principal Component Analysis (PCA) to reduce them to a smaller feature space (e.g., 128 dimensions).
This improves:

Training stability
Computational efficiency
Generalization of the ensemble model


7. Structural Risk Features (CRP‑Warner)
If available, static analysis features are added, such as:

Hidden minting behavior
Liquidity leakage patterns
Sell‑restriction mechanisms

These features represent structural vulnerabilities that may not be visible at the semantic level.

8. Feature Fusion
All extracted features are merged into a single feature vector per contract:

CodeBERT semantic features (after PCA)
Forta‑inspired heuristic scores
CRP‑Warner structural indicators

The resulting dataset combines semantic, lexical, and structural signals.

9. Model Training with LightGBM
The combined features are standardized and split into training and test sets.
A LightGBM binary classifier is trained to predict whether a contract is malicious.
Key properties of this step:

Handles heterogeneous feature types well
Supports class imbalance via weighting
Efficient enough for large‑scale or near‑real‑time use


10. Optional Soft‑Cascade Overrides
In some versions of the script:

Extremely high‑risk contracts (top percentile of heuristic scores) are force‑classified as scams
Extremely low‑risk contracts are force‑classified as benign

This implements a soft cascade, where rule‑based knowledge only overrides the model in extreme cases.

11. Evaluation and Output
The script evaluates the final predictions using:

Precision, recall, F1‑score
ROC‑AUC
Confusion matrices and threshold sensitivity analysis

Finally, it:

Saves the trained model and scaler
Exports the final feature table for inspection
Optionally produces plots comparing different detection methods


One‑Sentence Summary
This script takes smart contract source code, extracts semantic, heuristic, and structural risk signals, and fuses them using a LightGBM ensemble model to reliably detect rug‑pull scams.
