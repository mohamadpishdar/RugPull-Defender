# RugPull Detection Framework (Multi-Detector Benckmark)

This repository provides a reproducible framework for analyzing smart contracts involved in **rugpull attacks**. It supports:

- **Bytecode extraction** (from chain or local compilation)
- **Static smart contract analysis** with **CRPWarner** (CRPWarner + Gigahorse + Soufflé)
- **Evaluation against a manually labeled dataset**

The structure and workflow are designed for **research replication**, benchmarking, and extension to more detectors in the future.

---

## 🚀 Project Overview

Rugpulls are a form of scam where the contract deployers manipulate token ownership, liquidity, or privileged roles to drain user funds. This project analyzes contracts suspected of rugpull behavior using static bytecode-level reasoning tools and combines them with dynamic versions.

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

---

## 🧭 Roadmap

| Phase                            | Status  |
| -------------------------------- | ------- |
| CRPWarner setup                  | ✅ Done |
| Compile all contracts using solc | ✅ Done |
| Bytecode collection pipeline     | ✅ Done |
| CRPWarner batch analysis         | ✅ Done |
| Gather other bytecodes manually  | ✅ Done |
| Compare CRPWarner                | ✅ Done |

