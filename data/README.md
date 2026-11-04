# TM-RugPull data used in this repository

## Files

| File | Content |
|---|---|
| `dataset.xlsx` | One row per project (1,000 rows). Row *i* corresponds to source file `i.txt`. |
| `flatten_source_code_noheader.zip` | Flattened Solidity source of every project, `flatten_source_code/<i>.txt`. |
| `obfuscated_contracts_noheader.zip` | The same files after identifier renaming, `obfuscated_contracts/<i>.txt`. |
| `fold_assignment.json` | Stratified five-fold split, `{"<i>": fold}` with folds 0 to 4. |

## Labels and composition

* `class` is `scam` (rug pull, 599 projects) or `normal` (401 projects).
* The projects come from eight blockchains: Ethereum (633), BNB Smart Chain (321), Polygon (24), Arbitrum (12), Fantom (5, written as `FANTOM` or `FTM`), Cronos (2), Base (2), and Avalanche (1, `SNOW`).
* A project is labeled a rug pull only if, within a 72-hour observation window, it shows a near-total liquidity withdrawal or an equivalent exit pattern and the event is confirmed against public incident databases. Legitimate cases of liquidity removal, such as migrations or time-locked pools that reach their deadline, are labeled normal.

## Columns of `dataset.xlsx`

| Column | Meaning |
|---|---|
| `Project Title` | Project name |
| `MaxPrice (Quarter 1..4)` | Maximum token price in four consecutive quarters |
| `Blockchain`, `Blockchain Type` | Chain and its consensus family |
| `the number of Transactions` | Number of transactions of the token |
| `Token concentration ratio per holder`, `Total Variance`, `Variance of holders with more than 1% tokens`, `Token balance` | Holder-distribution statistics |
| `Sign`, `first deposits` | Additional on-chain indicators (see the TM-RugPull paper) |
| `Smart Contract (online)`, `smart Contract (offline)` | Hyperlinks to the contract source (online and offline copy) |
| `website`, `x profile` | Project web site and X (Twitter) profile |
| `class` | Label (`scam` or `normal`) |
| `project starting date`, `project end date` | Lifetime of the project |
| `Google results for ...` | Number of web search results at the start and in the middle of the project's lifetime |

Rug-Pull Defender uses only the source code and the `class` label. The remaining columns belong to the multimodal TM-RugPull dataset and are released for completeness; their exact definitions are given in the TM-RugPull paper.

## Preprocessing of the source files

The original flattened files began with a metadata comment (`// number:`, `// project:`, `// address:`, `// chainid:`). Because the project numbers follow the class order of the dataset, this header leaks the label. The released `*_noheader.zip` files have these lines removed with `pipeline/03_strip_metadata_header.py`; no other change was made to the sources. All experiments in the paper use these files.

The renamed sources were produced with `pipeline/04_obfuscate_identifiers.py`, which replaces every user-defined identifier with `_x` followed by six hexadecimal digits while keeping language keywords, built-ins, comments, and string literals intact.
