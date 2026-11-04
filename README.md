# Rug-Pull Defender

Code, data, and results for the paper **"Rug-Pull Defender: Detecting Rug-Pull Attacks via Multi-Modal Smart Contract Analysis"**.

Rug-Pull Defender detects rug-pull scams from smart contract code before deployment. It combines three modalities through a confidence-gated cascade:

| Modality | What it reads | Implementation |
|---|---|---|
| **W1** | Fine-tuned CodeBERT on the whole flattened Solidity contract (512-token windows, stride 256) | `codebert/` |
| **W2** | Forta-style lexical rules tailored to rug pulls, with fixed severity weights | `forta_rules/` |
| **W3** | CRPWarner flags on the runtime bytecode of the project's main contract | `crpwarner/` |

CodeBERT decides alone when it is confident. When its probability falls inside a gate band `[lo, hi]`, the final score is

```
score = (W1 + alpha * W2 + beta * W3_lean) / (1 + alpha + beta)
```

with `W3_lean = 0.8` if CRPWarner raises a retained flag and `0.2` otherwise. A contract is flagged as a rug pull when its score reaches `tau`. All five settings, the CodeBERT threshold, and the pruning of the Forta rules and CRPWarner flags are chosen on the training folds only (nested five-fold cross-validation).

## Main results (five-fold cross-validation, 1,000 contracts)

| Configuration | Clean accuracy | Clean balanced acc. | Renamed accuracy | Renamed balanced acc. |
|---|---|---|---|---|
| CodeBERT, threshold 0.5 | 0.814 | 0.797 | 0.641 | 0.555 |
| CodeBERT, tuned threshold | 0.805 | 0.815 | 0.766 | 0.745 |
| Forta-style rules, all eleven groups | 0.394 | 0.459 | 0.371 | 0.460 |
| CRPWarner, all three flags | 0.515 | 0.543 | 0.517 | 0.544 |
| Flat LightGBM on W1+W2+W3 | 0.823 | 0.814 | 0.733 | 0.710 |
| **Cascade W1+W2+W3** | **0.827** | **0.825** | **0.768** | **0.741** |

The full table (Table 2 of the paper) is in `results/table2.csv`, and every statistic quoted in the paper is in `results/stats.json`.

## Repository layout

```
data/
  dataset.xlsx                         TM-RugPull metadata and labels (1,000 projects)
  flatten_source_code_noheader.zip     flattened Solidity source of every project
  obfuscated_contracts_noheader.zip    the same sources after identifier renaming
  fold_assignment.json                 stratified five-fold split used in all experiments
pipeline/
  01_fetch_contracts.py                download verified source code from Etherscan-family explorers
  02_flatten_contracts.py              flatten multi-file sources into one file per project
  03_strip_metadata_header.py          remove the label-leaking metadata comment from every file
  04_obfuscate_identifiers.py          rename user-defined identifiers (_x + six hex digits)
codebert/
  codebert_fullcontract_cv.py          W1: fine-tuning and out-of-fold scoring (GPU, Colab-ready)
forta_rules/
  forta_rules.py                       W2: Forta-style rule set
crpwarner/
  prepare_bytecode.py                  select and compile the main contract of each project
  run_crpwarner.sh                     run CRPWarner (Gigahorse) on the bytecode
  collect_results.py                   turn CRPWarner output into one CSV per condition
  CRPWarner_rerun_colab.ipynb          the same steps as a Colab notebook
  README.md                            installation of Souffle 2.3, Gigahorse, and CRPWarner
cascade/
  evaluate.py                          nested tuning, Table 2, statistics, Figures 2 to 8
  near_duplicates.py                   MinHash analysis of template reuse across folds
figures/
  figure1_architecture.py              Figure 1 (architecture diagram)
results/
  codebert/{full,tail}/                out-of-fold CodeBERT probabilities, training logs, preprocessing statistics
  crpwarner/                           CRPWarner flags and compiler logs for both conditions
  table2.csv, table2.tex, stats.json   evaluation outputs
  near_duplicates.pkl                  contracts with a cross-fold near-duplicate
  figures/                             Figures 1 to 8 of the paper
```

## Reproducing the results

The evaluation step runs on a CPU in a few minutes and uses the stored CodeBERT and CRPWarner outputs:

```bash
pip install -r requirements.txt
python cascade/near_duplicates.py     # optional: template-reuse analysis
python cascade/evaluate.py            # Table 2, statistics, Figures 2 to 8
python figures/figure1_architecture.py
```

To regenerate the stored model outputs from scratch:

1. **Data preparation** (already done for the released files). `pipeline/03_strip_metadata_header.py` removes the metadata comment that encoded the dataset index, and `pipeline/04_obfuscate_identifiers.py` produces the renamed sources.
2. **W1, CodeBERT.** Run `codebert/codebert_fullcontract_cv.py` on a GPU. On Google Colab, upload the three files from `data/` to `/content` and run the script with a T4 GPU (about 4 to 6 hours). Outside Colab, set `RPD_DATA_DIR`, `RPD_USE_DRIVE=0`, and `RPD_OUT_DIR`. The script runs both the whole-contract model and the last-512-token baseline on the folds in `data/fold_assignment.json`, and writes `codebert_fullcv_probs.csv`, `training_log.csv`, and `preprocessing_stats.csv` for each mode. Copy these into `results/codebert/{full,tail}/`.
3. **W3, CRPWarner.** Follow `crpwarner/README.md`. It compiles the main contract of each project, runs CRPWarner, and writes `results/crpwarner/crpwarner_results_{clean,obfuscated}.csv`.
4. Run `cascade/evaluate.py`.

## Dataset

TM-RugPull contains 1,000 token projects (599 rug pulls, 401 normal projects) from eight blockchains, labeled through a forensic protocol cross-checked against public incident databases. See `data/README.md` for the columns and the labeling protocol. The dataset was introduced in:

> F. Shoaei et al., *TM-RugPull: A Temporally Sound, Multimodal Dataset for Early Detection of Rug Pulls Across the Tokenized Ecosystem*, arXiv:2602.21529, 2026.

## Third-party tools

* CodeBERT: `microsoft/codebert-base` from Hugging Face (Feng et al., 2020).
* CRPWarner: https://github.com/CRPWarner/RugPull (Lin et al., IEEE TSE 2024), run on Gigahorse with Souffle 2.3.
* The W2 rules are written in the style of the Forta monitoring rules. They are not the official Forta detection bots.

## Citation

If you use this code or the results, please cite the Rug-Pull Defender paper and the TM-RugPull dataset paper.
