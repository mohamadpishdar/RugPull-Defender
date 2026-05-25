## Overview

The following is a Python code that executes an end-to-end detection of the rug-pull pattern in smart contracts. The program reads smart contract source code files, identifies various risk factors, and creates a machine learning model from the risk factors to detect whether a smart contract is a rug pull scam or a safe one.

## What does the Python code do?

### 1. Environment Setup and Dependencies

Before running any code, we first install and import all necessary libraries, including:

- PyTorch and Transformers for CodeBERT embeddings  
- LightGBM for the ensemble classifier  
- Pandas and NumPy for data processing  
- Scikit‑learn for PCA, scaling, and evaluation  
- RAR/ZIP utilities to extract smart contract source files  

This allows for the entire pipeline to be executed within a single notebook/execution environment, like Google Colab.

### 2. Input Data Loading

The script expects three main inputs:

- An Excel file containing:
  - Smart contract identifiers  
  - Ground‑truth labels (scam / normal)  

- ZIP or RAR archive containing Solidity source code of the contracts.  
- (Optional) Output from CRP-Warner tool containing static risk scores.  

Identifiers of all contracts are converted to strings.

### 3. Source Code Extraction

Contract source code archive is unpacked to a local directory.  
Every contract's file name is associated with the identifier of the contract.  

Missing contract's source code leads to handling of an error gracefully – an empty set of features.

### 4. Forta-Inspired Risk Scoring Using Heuristics

We use a simplified version of the Forta risk scoring based on heuristics to score the risk level of every smart contract based on patterns in the source code such as:

- Owner‑only privileges (onlyOwner)  
- Token minting (mint)  
- Liquidity withdrawal (withdraw, drain)  
- Blacklisting or fee manipulation  
- Low‑level calls and inline assembly  

Every pattern has its weighted risk value.  
The output becomes a numeric heuristics-based risk feature, which represents risk signals based on knowledge-based detection.

In contrast to Forta, this layer only mimics the rule-based engine logic, but in a much simpler manner.

### 5. CodeBERT Semantic Embeddings

The source code of each smart contract is passed through CodeBERT:

- Code is tokenized and truncated to at most 512 tokens  
- The code is encoded by CodeBERT’s transformer-based model  
- Average the token embeddings to obtain a 768‑dimensional vector representation of the code  

This provides a semantic understanding of the code even if the naming convention is obscure or deceptive.

Zero vectors are used for contracts without source code.

### 6. Dimensionality Reduction Using PCA

As CodeBERT embeddings are high-dimensional, PCA is performed on them to create low-dimensional features (say, 128 dimensions).  

This helps:

- Training stability  
- Computational efficiency  
- Generalization of the ensemble model  

### 7. Structural Risk Features (CRP‑Warner)

If available, static analysis features are added, such as:

- Hidden minting behavior  
- Liquidity leakage patterns  
- Sell‑restriction mechanisms  

These are vulnerabilities inherent in the structure which are not immediately apparent at the semantic level.

### 8. Feature Fusion

All extracted features are aggregated into one feature vector per contract:

- CodeBERT semantic features (post-PCA)  
- Forta-inspired heuristic scores  
- CRP-Warner structural features  

The output feature vectors thus incorporate semantic, lexical and structural information.

### 9. LightGBM Model Training

The combined feature set is normalized and split into train/test subsets.  
A binary LightGBM classifier is trained on the data, predicting the presence of malice.

Properties of this step:

- Effective with mixed feature types  
- Ability to account for imbalanced classes via weighting  
- Suitably efficient to be applicable to scale  

### 10. Optional Soft Cascade Overrides

Optional in some implementations of the code:

- Contracts with extremely high risk (in terms of heuristic score) are manually classified as scams  
- Contracts with very low risk are manually classified as benign  

This represents a soft cascade, whereby rule-based domain knowledge overrides model decisions only in extreme cases.

### 11. Evaluation and Output

The script performs an evaluation using the final results based on:

- Precision, Recall and F1-score  
- ROC-AUC  
- Confusion matrices and thresholding sensitivity analysis  

Finally, it:

- Outputs and saves the fitted model and normalization scaler  
- Outputs the final table of feature vectors  
- Optionally outputs visualizations comparing detection approaches  
