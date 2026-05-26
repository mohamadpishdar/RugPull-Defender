# RugPull Defender Static Analysis Part

The present repository provides the tools for analyzing smart contracts involved in **rugpull attacks**. Specifically, it is possible to:

- Extract **bytecode** from chain or locally compiled contract
- Perform **static smart contract analysis** with **CRPWarner** 
- Compare with **manually annotated dataset**

The approach is designed for reproducing research, benchmarking, and potentially adding more contracts later.

---

## Project Overview

Rug pulls constitute yet another form of scams, where the creators of a contract use certain tactics that can help them steal users' funds by manipulating ownership or other aspects. This paper will explore suspected smart contracts capable of performing rug pull attacks, through static analysis of bytecodes, which is complemented with dynamic ones.

The workflow:

1. Retrieve contract bytecode (ideally on-chain)
2. Perform CRPWarner and additional static analyses
3. Evaluate results against manual annotations from our data set
4. Metrics and findings

---

## Repository Structure

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

