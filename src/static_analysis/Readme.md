# RugPull Defender Static Analysis Part

This repository presents a reproducible approach to the analysis of smart contracts used in **rugpull attacks**. It allows:

- **Bytecode extraction** (from chain or local compilation)
- **Static smart contract analysis** with **CRPWarner** 
- **Evaluation against a manually labeled dataset**

The workflow is geared towards **replicating research**, benchmarking, and scaling to incorporate additional contracts in the future.

---

## 🚀 Project Overview

Rug pulls represent another type of scam, whereby contract creators manipulate token ownership or other factors to transfer user assets. In this paper, we will analyze contract codes suspected to carry out rug pulls using static analysis on bytecodes, which will be combined with their dynamic counterparts.

The workflow:

1. Collect contract bytecode (preferably from-chain)
2. Run CRPWarner and additional detectors
3. Compare results against expert annotations from our dataset
4. Report metrics and insights

---

## 📂 Repository Structure

```text
├── README.md ← You are here
│
├── docs/
│ └── setup_crpwarner.md ← Full CRPWarner setup instructions
│
├── scripts/
│ ├── compile_all_solcselect.py ← Compile Solidity with correct versioning
│ ├── fetch_bytecode.py ← Pull on-chain runtime bytecode
│ ├── run_crpwarner.py ← Execute CRPWarner on the given bytecodes and export the batch results as Excel files
│ └── compare_crpwarner.py ← Produces final benchmark tables
│
├── dataset/
│ ├── all_bytecodes/ ← Runtime bytecode
│ └── crpwarner_results/ ← Output of "scripts/run_crpwarner.py"
│
└── results/
  ├── crpwarner_results_all.xlsx ← CRPWarner results for all bytecodes
  └── metrics/ ← Precision/Recall/F1 for each detector
```

