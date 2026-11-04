#!/usr/bin/env python3
"""
Rug-Pull Defender: evaluation of the confidence-gated cascade.

This script reproduces every number in Section 5 of the paper (Table 2,
Figures 2 to 8, and the statistics quoted in the text) from three inputs:

  * the out-of-fold CodeBERT probabilities (codebert/codebert_fullcontract_cv.py),
  * the flattened sources, on which the Forta-style rules (W2) are evaluated,
  * the CRPWarner flags of each project's main contract (crpwarner/).

Protocol
--------
All results come from stratified five-fold cross-validation over the 1,000
contracts of TM-RugPull. For each test fold k, every data-dependent choice is
made on the other four folds only:

  1. Pruning of the auxiliary modalities. A Forta rule group or a CRPWarner
     flag is kept when it fires in at least MIN_FIRES training contracts and
     the rug-pull share among those contracts exceeds the training base rate
     by MARGIN. Rule weights are never changed.
  2. The tuned CodeBERT threshold, chosen by balanced accuracy.
  3. The five cascade settings (gate band [lo, hi], Forta weight alpha,
     CRPWarner weight beta, decision threshold tau), chosen by an exhaustive
     grid search that maximizes balanced accuracy.

Renamed contracts are recognized by a fixed rule (more than 20 identifiers of
the form `_x` plus six hexadecimal digits, the pattern written by
pipeline/04_obfuscate_identifiers.py). They receive a second threshold and a
second cascade configuration, tuned by the same nested search on the renamed
versions of the training folds.

Cascade rule (applied per contract):
    if lo <= W1 <= hi:  score = (W1 + alpha * W2 + beta * W3_lean) / (1 + alpha + beta)
    else:               score = W1
    flag a rug pull when score >= tau
where W3_lean is 0.8 if CRPWarner raises one of the retained flags and 0.2 otherwise.

Usage (from the repository root):
    python cascade/evaluate.py

Outputs (in results/):
    table2.csv, table2.tex, stats.json, figures/Figure{2..8}_*.png
"""

import argparse
import itertools
import json
import os
import pickle
import re
import sys
import zipfile
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP

import lightgbm as lgb
import matplotlib
import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.metrics import f1_score, precision_recall_curve, roc_auc_score, roc_curve

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "forta_rules"))
from forta_rules import RULES, in_code_context  # noqa: E402

MIN_FIRES, MARGIN = 10, 0.05
OBF_PATTERN, OBF_MIN = re.compile(r"\b_x[0-9a-f]{6}\b"), 20
CONDITIONS = ("clean", "obfuscated")
GRID = [c for c in itertools.product(np.round(np.arange(0.2, 0.61, 0.05), 2),      # lo
                                     np.round(np.arange(0.4, 0.91, 0.05), 2),      # hi
                                     [0, 0.25, 0.5, 1.0],                          # alpha
                                     [0, 0.25, 0.5, 1.0, 1.5, 2.0],                # beta
                                     np.round(np.arange(0.35, 0.76, 0.05), 2))     # tau
        if c[0] < c[1]]


# ----------------------------------------------------------------------------- helpers
def read_zip(path):
    with zipfile.ZipFile(path) as z:
        return {int(re.search(r"(\d+)\.txt$", n).group(1)): z.read(n).decode("utf8", "ignore")
                for n in z.namelist() if n.endswith(".txt")}


def balanced_accuracy(y, pred):
    return 0.5 * ((pred & (y == 1)).sum() / (y == 1).sum() + (~pred & (y == 0)).sum() / (y == 0).sum())


def cascade(p1, p2, flag, lo, hi, alpha, beta, tau):
    """Return (score, prediction, gate mask) of the cascade for one configuration."""
    lean = np.where(flag, 0.8, 0.2)
    gate = (p1 >= lo) & (p1 <= hi)
    score = np.where(gate, (p1 + alpha * p2 + beta * lean) / (1 + alpha + beta), p1)
    return score, score >= tau, gate


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def fmt3(v):
    return str(Decimal(repr(round(float(v), 10))).quantize(Decimal("0.001"), ROUND_HALF_UP))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--codebert", default=os.path.join(ROOT, "results", "codebert"))
    ap.add_argument("--crpwarner", default=os.path.join(ROOT, "results", "crpwarner"))
    ap.add_argument("--out", default=os.path.join(ROOT, "results"))
    args = ap.parse_args()
    fig_dir = os.path.join(args.out, "figures")
    os.makedirs(fig_dir, exist_ok=True)

    # ------------------------------------------------------------------------- data
    meta = pd.read_excel(os.path.join(args.data, "dataset.xlsx"))
    meta["number"] = range(1, len(meta) + 1)
    labels = pd.Series((meta["class"] == "scam").astype(int).values, index=meta["number"])
    nums = meta["number"].values
    y = labels.loc[nums].values
    folds = json.load(open(os.path.join(args.data, "fold_assignment.json")))
    fo = pd.Series({int(k): v for k, v in folds.items()}).loc[nums].values
    src = {"clean": read_zip(os.path.join(args.data, "flatten_source_code_noheader.zip")),
           "obfuscated": read_zip(os.path.join(args.data, "obfuscated_contracts_noheader.zip"))}

    def mcnemar(a, b):
        n10 = int(((a == y) & (b != y)).sum())
        n01 = int(((a != y) & (b == y)).sum())
        return n10, n01, binomtest(min(n10, n01), max(1, n10 + n01), 0.5).pvalue

    def metrics(pred, score):
        return dict(acc=(pred == y).mean(), f1=f1_score(y, pred), auc=roc_auc_score(y, score),
                    fpr=(pred & (y == 0)).sum() / (y == 0).sum(), fnr=(~pred & (y == 1)).sum() / (y == 1).sum(),
                    fp=int((pred & (y == 0)).sum()), fn=int((~pred & (y == 1)).sum()))

    # W1: out-of-fold CodeBERT probabilities. The window aggregation (max, mean,
    # mean of the top three) is chosen on the inner validation rows only.
    w1, agg_used = {}, {}
    for mode in ("full", "tail"):
        probs = pd.read_csv(os.path.join(args.codebert, mode, "codebert_fullcv_probs.csv"))
        inner = probs[probs.split == "inner_val"]
        acc = {a: ((inner[a] >= 0.5) == inner.y).mean() for a in ("p_max", "p_mean", "p_top3")}
        agg = max(acc, key=acc.get)
        agg_used[mode] = agg
        print(f"{mode}: inner-validation accuracy by aggregation {({k: round(v, 3) for k, v in acc.items()})} -> {agg}")
        w1[mode] = {c: probs[(probs.split == "test") & (probs.condition == c)].set_index("number")[agg].loc[nums].values
                    for c in CONDITIONS}
    P1, PT = w1["full"], w1["tail"]

    # W2: Forta-style rule hits per contract.
    hits = {c: np.array([[in_code_context(src[c][n], p) for p, _ in RULES] for n in nums]) for c in CONDITIONS}
    weights = np.array([w for _, w in RULES])
    p2_all = {c: (hits[c] * weights).sum(1) / weights.sum() for c in CONDITIONS}

    # W3: CRPWarner flags of the main contract.
    crp = {c: pd.read_csv(os.path.join(args.crpwarner, f"crpwarner_results_{c}.csv")).set_index("GroupID") for c in CONDITIONS}
    crp3 = {c: crp[c].loc[nums, ["HiddenMint", "LeakingToken", "LimitingSell"]].fillna(0).values > 0 for c in CONDITIONS}
    fl_all = {c: crp[c].loc[nums, "RugPull"].astype(bool).values for c in CONDITIONS}

    # ------------------------------------------------------------------------- pruning on training folds
    def prune(fired, margin=MARGIN):
        kept = {}
        for k in range(5):
            tr = fo != k
            base = y[tr].mean()
            kept[k] = tuple(j for j in range(fired.shape[1])
                            if fired[tr, j].sum() >= MIN_FIRES and y[tr][fired[tr, j]].mean() > base + margin)
        return kept

    kept_rules, kept_flags = prune(hits["clean"]), prune(crp3["clean"])
    print("retained Forta rule groups per fold:", kept_rules)
    print("retained CRPWarner flags per fold:  ", kept_flags)
    # The selection is identical in every fold, so a single set is applied below.
    assert len(set(kept_rules.values())) == 1 and len(set(kept_flags.values())) == 1
    keep = np.array(kept_rules[0])
    kc = list(kept_flags[0])
    P2 = {c: (hits[c][:, keep] * weights[keep]).sum(1) / weights[keep].sum() for c in CONDITIONS}
    FL = {c: crp3[c][:, kc].any(1) for c in CONDITIONS}

    # ------------------------------------------------------------------------- nested tuning
    def tune_cascade(cond, restrict=lambda c: True):
        cfg = {}
        for k in range(5):
            tr = fo != k
            best, best_v = None, -1
            for c in GRID:
                if not restrict(c):
                    continue
                v = balanced_accuracy(y[tr], cascade(P1[cond][tr], P2[cond][tr], FL[cond][tr], *c)[1])
                if v > best_v + 1e-12:
                    best_v, best = v, c
            cfg[k] = tuple(float(x) for x in best)
        return cfg

    def tune_threshold(p):
        th = {}
        for k in range(5):
            tr = fo != k
            grid = np.round(np.arange(0.3, 0.96, 0.01), 2)
            th[k] = float(grid[int(np.argmax([balanced_accuracy(y[tr], p[tr] >= t) for t in grid]))])
        return th

    def apply_cfg(cfg, p1, p2, fl):
        score, pred, gate = np.zeros(len(y)), np.zeros(len(y), bool), np.zeros(len(y), bool)
        for k, c in cfg.items():
            m = fo == k
            score[m], pred[m], gate[m] = cascade(p1[m], p2[m], fl[m], *c)
        return score, pred, gate

    CF = {"FINAL": tune_cascade("clean"), "W1+W3": tune_cascade("clean", lambda c: c[2] == 0),
          "W1+W2": tune_cascade("clean", lambda c: c[3] == 0)}
    CFO = {"FINAL": tune_cascade("obfuscated"), "W1+W3": tune_cascade("obfuscated", lambda c: c[2] == 0),
           "W1+W2": tune_cascade("obfuscated", lambda c: c[3] == 0)}
    TH, THO = tune_threshold(P1["clean"]), tune_threshold(P1["obfuscated"])
    renamed = {c: np.array([len(OBF_PATTERN.findall(src[c][n])) > OBF_MIN for n in nums]) for c in CONDITIONS}
    print("renaming detector: share flagged", {c: float(renamed[c].mean()) for c in CONDITIONS})

    stats = {"retained_rules": {k: list(map(int, v)) for k, v in kept_rules.items()},
             "retained_flags": {k: list(map(int, v)) for k, v in kept_flags.items()},
             "cfg_clean": CF, "cfg_renamed": CFO, "thr_clean": TH, "thr_renamed": THO,
             "renaming_detector": {c: float(renamed[c].mean()) for c in CONDITIONS}, "aggregation": agg_used}

    # ------------------------------------------------------------------------- all configurations
    rows, PRED, SCORE, GATE = [], {}, {}, {}
    for c in CONDITIONS:
        D = {}
        D["W1 (CodeBERT, full contract)"] = (P1[c], P1[c] >= 0.5)
        thr = np.array([(THO if r else TH)[k] for k, r in zip(fo, renamed[c])])
        D["W1 (CodeBERT, full contract, tuned threshold)"] = (P1[c], P1[c] >= thr)
        D["W1 (CodeBERT, last 512 tokens)"] = (PT[c], PT[c] >= 0.5)
        D["W2 (Forta alone)"] = (P2[c], P2[c] >= 0.5)
        D["W2 (Forta, all eleven rule groups)"] = (p2_all[c], p2_all[c] >= 0.5)
        D["W3 (CRPWarner alone)"] = (FL[c].astype(float), FL[c])
        D["W3 (CRPWarner, all three flags)"] = (fl_all[c].astype(float), fl_all[c])
        blend = (0.5 * P2[c] + np.where(FL[c], 0.8, 0.2)) / 1.5
        D["W2+W3 (blended, no gate)"] = (blend, blend >= 0.5)
        flat = np.zeros(len(y))                    # flat LightGBM on the concatenated signals
        for k in range(5):
            tr = fo != k
            X = lambda cc, m: np.c_[logit(P1[cc][m]), P2[cc][m], crp3[cc][m].astype(float)]  # noqa: E731
            for source, is_renamed in (("clean", False), ("obfuscated", True)):
                te = (fo == k) & (renamed[c] == is_renamed)
                if not te.any():
                    continue
                model = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=15,
                                           min_child_samples=10, verbose=-1, random_state=42)
                flat[te] = model.fit(X(source, tr), y[tr]).predict_proba(X(c, te))[:, 1]
        D["W1+W2+W3 (flat LightGBM, concatenated)"] = (flat, flat >= 0.5)
        for name, key in (("W1+W2 (cascade)", "W1+W2"), ("W1+W3 (cascade)", "W1+W3"), ("W1+W2+W3 (cascade, FINAL)", "FINAL")):
            s1, p1_, g1 = apply_cfg(CF[key], P1[c], P2[c], FL[c])
            s2, p2_, g2 = apply_cfg(CFO[key], P1[c], P2[c], FL[c])
            m = renamed[c]
            D[name] = (np.where(m, s2, s1), np.where(m, p2_, p1_))
            if key == "FINAL":
                GATE[c] = np.where(m, g2, g1)
        for name, (score, pred) in D.items():
            mt = metrics(pred, score)
            rows.append(dict(Combination=name, Condition=c.capitalize(), Accuracy=mt["acc"], BalAcc=balanced_accuracy(y, pred),
                             F1=mt["f1"], AUC=mt["auc"], FPR=mt["fpr"], FNR=mt["fnr"], FP=mt["fp"], FN=mt["fn"]))
            PRED[(name, c)], SCORE[(name, c)] = pred, score
    T = pd.DataFrame(rows)
    T.to_csv(os.path.join(args.out, "table2.csv"), index=False)
    pd.set_option("display.width", 250)
    print(T.round(3).to_string(index=False))

    # ------------------------------------------------------------------------- statistics quoted in the text
    FIN, CB, CBT = "W1+W2+W3 (cascade, FINAL)", "W1 (CodeBERT, full contract)", "W1 (CodeBERT, full contract, tuned threshold)"
    for c in CONDITIONS:
        for other in (CB, CBT, "W1 (CodeBERT, last 512 tokens)", "W1+W3 (cascade)", "W1+W2 (cascade)",
                      "W2 (Forta alone)", "W3 (CRPWarner alone)", "W1+W2+W3 (flat LightGBM, concatenated)"):
            stats[f"mcnemar.{c}.FINAL_vs_{other}"] = mcnemar(PRED[(FIN, c)], PRED[(other, c)])
        stats[f"mcnemar.{c}.full_vs_last512"] = mcnemar(PRED[(CB, c)], PRED[("W1 (CodeBERT, last 512 tokens)", c)])
        g, b, e = GATE[c], PRED[(CB, c)], PRED[(FIN, c)]
        stats[f"gate.{c}"] = dict(share=float(g.mean()), n=int(g.sum()), acc_codebert=float((b[g] == y[g]).mean()),
                                  acc_cascade=float((e[g] == y[g]).mean()),
                                  false_positives_fixed=int((g & b & ~e & (y == 0)).sum()),
                                  rug_pulls_lost=int((g & b & ~e & (y == 1)).sum()),
                                  rug_pulls_recovered=int((g & ~b & e & (y == 1)).sum()),
                                  normals_lost=int((g & ~b & e & (y == 0)).sum()),
                                  crp_flag_rate_rug_pulls=float(FL[c][g & (y == 1)].mean()),
                                  crp_flag_rate_normals=float(FL[c][g & (y == 0)].mean()))
        stats[f"forta_mean.{c}"] = [float(P2[c][y == 1].mean()), float(P2[c][y == 0].mean())]
        stats[f"uncertain_share.{c}"] = float(((SCORE[(FIN, c)] > 0.2) & (SCORE[(FIN, c)] < 0.8)).mean())
        for name in ("W2 (Forta alone)", CB, FIN):
            fpr, tpr, _ = roc_curve(y, SCORE[(name, c)])
            prec, rec, _ = precision_recall_curve(y, SCORE[(name, c)])
            stats[f"curves.{c}.{name}"] = dict(tpr_at_fpr10=float(tpr[fpr <= 0.10].max()),
                                               precision_at_recall50=float(prec[rec >= 0.5].max()),
                                               precision_at_recall90=float(prec[rec >= 0.9].max()))
    unique = Counter()
    for c in CONDITIONS:
        a, b, d3 = PRED[(CB, c)] == y, PRED[("W2 (Forta alone)", c)] == y, FL[c] == y
        s = a.astype(int) + b + d3
        unique.update(codebert_only=int(((s == 1) & a).sum()), forta_only=int(((s == 1) & b).sum()),
                      crpwarner_only=int(((s == 1) & d3).sum()), exactly_two=int((s == 2).sum()),
                      all_three=int((s == 3).sum()), none=int((s == 0).sum()))
    stats["which_modalities_correct"] = dict(unique)
    fold_acc = pd.DataFrame([dict(fold=k, **{f"{mode}_{c}": float(((P[c][fo == k] >= 0.5) == y[fo == k]).mean())
                                             for mode, P in (("full", P1), ("tail", PT)) for c in CONDITIONS},
                                  **{f"cascade_{c}": float((PRED[(FIN, c)][fo == k] == y[fo == k]).mean()) for c in CONDITIONS})
                             for k in range(5)])
    stats["fold_accuracy"] = fold_acc.to_dict("list")
    # Sensitivity of the clean-code result to the pruning margin.
    sens = {}
    for margin in (0.0, 0.02, 0.05, 0.10):
        kr, kf = prune(hits["clean"], margin), prune(crp3["clean"], margin)
        pred = np.zeros(len(y), bool)
        for k in range(5):
            kk = np.array(kr[k])
            p2 = (hits["clean"][:, kk] * weights[kk]).sum(1) / weights[kk].sum()
            fl = crp3["clean"][:, list(kf[k])].any(1) if kf[k] else np.zeros(len(y), bool)
            tr, te = fo != k, fo == k
            best = max(GRID, key=lambda cf: balanced_accuracy(y[tr], cascade(P1["clean"][tr], p2[tr], fl[tr], *cf)[1]))
            pred[te] = cascade(P1["clean"][te], p2[te], fl[te], *best)[1]
        sens[str(margin)] = dict(accuracy=float((pred == y).mean()), mcnemar_vs_tuned_codebert=mcnemar(pred, PRED[(CBT, "clean")]))
    stats["pruning_margin_sensitivity_clean"] = sens
    # Accuracy on contracts without a cross-fold near-duplicate (cascade/near_duplicates.py).
    dup_path = os.path.join(args.out, "near_duplicates.pkl")
    if os.path.exists(dup_path):
        dup = set(pickle.load(open(dup_path, "rb")))
        nd = np.array([n not in dup for n in nums])
        stats["no_near_duplicate"] = {f"{name}|{c}": float((PRED[(name, c)][nd] == y[nd]).mean())
                                      for c in CONDITIONS for name in (CB, CBT, "W1 (CodeBERT, last 512 tokens)", FIN)}
        stats["no_near_duplicate"]["n"] = int(nd.sum())
    json.dump(stats, open(os.path.join(args.out, "stats.json"), "w"), indent=1,
              default=lambda o: o.item() if hasattr(o, "item") else str(o))

    # ------------------------------------------------------------------------- Table 2 (LaTeX)
    lines = [r"\begin{tabular}{llrrrrrr}", r"\toprule",
             r"Combination & Condition & Accuracy & Balanced acc. & F1 & AUC & FPR & FNR \\", r"\midrule"]
    for name in dict.fromkeys(T.Combination):
        for i, (_, r) in enumerate(T[T.Combination == name].iterrows()):
            first = (r"\multirow{2}{*}{" + name + "}") if i == 0 else ""
            lines.append(f"{first} & {r.Condition} & {fmt3(r.Accuracy)} & {fmt3(r.BalAcc)} & {fmt3(r.F1)} & "
                         f"{fmt3(r.AUC)} & {fmt3(r.FPR)} & {fmt3(r.FNR)} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    open(os.path.join(args.out, "table2.tex"), "w").write("\n".join(lines))

    # ------------------------------------------------------------------------- figures
    plt.rcParams.update({"font.size": 13, "axes.grid": True, "grid.color": "#dddddd",
                         "axes.edgecolor": "#bbbbbb", "axes.axisbelow": True})
    DET = [("Forta", "W2 (Forta alone)", "#2a78d6"), ("CRP", "W3 (CRPWarner alone)", "#e8673a"),
           ("CodeBERT", CB, "#1db07c"), ("Ensemble", FIN, "#c88500")]
    TITLE = {"clean": "Clean contracts", "obfuscated": "Obfuscated contracts"}

    fig, ax = plt.subplots(1, 2, figsize=(20, 6.6), sharey=True)                       # Figure 2
    for a, c in zip(ax, CONDITIONS):
        x = np.arange(4)
        for i, (lab, name, col) in enumerate(DET):
            r = T[(T.Combination == name) & (T.Condition == c.capitalize())].iloc[0]
            vals = [r.Accuracy, r.BalAcc, r.F1, r.AUC]
            bars = a.bar(x + (i - 1.5) * 0.2, vals, 0.2, color=col, label=lab, edgecolor="white")
            for bar, v in zip(bars, vals):
                a.text(bar.get_x() + bar.get_width() / 2, v + 0.012, f"{v:.2f}", ha="center", fontsize=10.5)
        a.set_xticks(x)
        a.set_xticklabels(["Accuracy", "Balanced acc.", "F1-score", "AUC"])
        a.set_title(TITLE[c], fontsize=18)
        a.set_ylim(0, 1.0)
    ax[0].set_ylabel("Score")
    ax[0].legend(loc="upper left", fontsize=12, ncol=2)
    plt.tight_layout(); plt.savefig(os.path.join(fig_dir, "Figure2_comparative_metrics.png"), dpi=220); plt.close()

    for fname, kind in (("Figure3_ROC", "roc"), ("Figure4_PR", "pr")):                  # Figures 3 and 4
        fig, ax = plt.subplots(1, 2, figsize=(14, 6))
        for a, c in zip(ax, CONDITIONS):
            for lab, name, col in DET:
                sc = SCORE[(name, c)].astype(float)
                ls = "--" if lab == "Ensemble" else "-"
                if kind == "roc":
                    fpr, tpr, _ = roc_curve(y, sc)
                    a.plot(fpr, tpr, color=col, lw=2.2, ls=ls, label=f"{lab} (AUC {roc_auc_score(y, sc):.3f})")
                else:
                    prec, rec, _ = precision_recall_curve(y, sc)
                    a.step(rec, prec, where="post", color=col, lw=2.2, ls=ls, label=lab)
            if kind == "roc":
                a.plot([0, 1], [0, 1], "--", color="#999999", lw=1)
                a.set_xlabel("False positive rate"); a.set_ylabel("True positive rate")
                a.legend(fontsize=10.5, loc="lower right")
            else:
                a.axhline(y.mean(), ls="--", color="#999999", lw=1, label=f"Prevalence ({y.mean():.3f})")
                a.set_xlabel("Recall"); a.set_ylabel("Precision"); a.set_ylim(0.2, 1.02)
                a.legend(fontsize=10.5, loc="lower left", ncol=2)
            a.set_title(TITLE[c], fontsize=16)
        plt.tight_layout(); plt.savefig(os.path.join(fig_dir, f"{fname}.png"), dpi=220); plt.close()

    fig, ax = plt.subplots(1, 2, figsize=(18, 6.6))                                     # Figure 5
    x = np.arange(5)
    for i, (key, col, lab) in enumerate((("full_clean", "#1db07c", "Whole contract, clean"),
                                         ("full_obfuscated", "#8fd9bd", "Whole contract, obfuscated"),
                                         ("tail_clean", "#c88500", "Last 512 tokens, clean"),
                                         ("tail_obfuscated", "#e8c27a", "Last 512 tokens, obfuscated"))):
        bars = ax[0].bar(x + (i - 1.5) * 0.2, fold_acc[key], 0.2, color=col, label=lab, edgecolor="white")
        for bar, v in zip(bars, fold_acc[key]):
            ax[0].text(bar.get_x() + bar.get_width() / 2, v + 0.006, f"{v * 100:.0f}", ha="center", fontsize=9)
    ax[0].set_xticks(x); ax[0].set_xticklabels([f"fold {k + 1}" for k in range(5)]); ax[0].set_ylim(0.5, 0.92)
    ax[0].set_ylabel("CodeBERT test accuracy (threshold 0.5)")
    ax[0].set_title("(a) CodeBERT accuracy on each held-out fold", fontsize=15)
    ax[0].legend(fontsize=10.5, ncol=2, loc="upper left")
    log = pd.read_csv(os.path.join(args.codebert, "full", "training_log.csv"))
    for k, col in zip(range(5), ["#2a78d6", "#e8673a", "#1db07c", "#c88500", "#7a5cc4"]):
        t = log[log.fold == k]
        ax[1].plot(t.epoch, t.val_acc_p_mean, "-o", color=col, lw=2, ms=5, label=f"fold {k + 1}")
    ax[1].set_xlabel("Epoch"); ax[1].set_ylabel("Inner validation accuracy (80 contracts)")
    ax[1].set_title("(b) Validation accuracy during fine-tuning, whole contract", fontsize=15)
    ax[1].legend(fontsize=11, ncol=2)
    plt.tight_layout(); plt.savefig(os.path.join(fig_dir, "Figure5_seed_stability.png"), dpi=220); plt.close()

    fig, ax = plt.subplots(1, 2, figsize=(13, 5.6))                                     # Figure 6
    for a, c in zip(ax, CONDITIONS):
        e = PRED[(FIN, c)]
        cm = np.array([[((e == 0) & (y == 0)).sum(), ((e == 1) & (y == 0)).sum()],
                       [((e == 0) & (y == 1)).sum(), ((e == 1) & (y == 1)).sum()]])
        cn = cm / cm.sum(1, keepdims=True)
        a.imshow(cn, cmap="YlOrBr", vmin=0, vmax=1); a.grid(False)
        for i in range(2):
            for j in range(2):
                a.text(j, i, f"{cn[i, j]:.3f}\n({cm[i, j]})", ha="center", va="center", fontsize=15,
                       color="white" if cn[i, j] > 0.55 else "black")
        a.set_xticks([0, 1]); a.set_xticklabels(["Normal", "Rug pull"])
        a.set_yticks([0, 1]); a.set_yticklabels(["Normal", "Rug pull"])
        a.set_xlabel("Predicted"); a.set_ylabel("Actual")
        r = T[(T.Combination == FIN) & (T.Condition == c.capitalize())].iloc[0]
        a.set_title(f"{TITLE[c]}\nFPR = {r.FPR:.3f}, FNR = {r.FNR:.3f}", fontsize=14)
    plt.tight_layout(); plt.savefig(os.path.join(fig_dir, "Figure6_confusion_matrix.png"), dpi=220); plt.close()

    band = {c: Counter((v[0], v[1]) for v in (CF if c == "clean" else CFO)["FINAL"].values()).most_common(1)[0][0]
            for c in CONDITIONS}
    thresholds = np.round(np.arange(0.05, 0.951, 0.01), 2)
    fig, ax = plt.subplots(1, 2, figsize=(16, 6), sharey=True)                          # Figure 7
    for a, c in zip(ax, CONDITIONS):
        for lab, name, col in DET:
            sc = SCORE[(name, c)].astype(float)
            a.plot(thresholds, [((sc >= t) == y).mean() for t in thresholds], color=col, lw=2.2, label=lab)
        a.axvspan(*band[c], color="#999999", alpha=0.15, label="Gate band (most frequent across folds)")
        a.axvline(0.5, ls=":", color="#555555", lw=1)
        a.set_title(TITLE[c], fontsize=16); a.set_xlabel("Decision threshold"); a.set_ylim(0.3, 0.9)
    ax[0].set_ylabel("Accuracy")
    handles, labs = ax[0].get_legend_handles_labels()
    fig.legend(handles, labs, loc="lower center", ncol=5, fontsize=12, frameon=False)
    plt.tight_layout(rect=(0, 0.08, 1, 1)); plt.savefig(os.path.join(fig_dir, "Figure7_accuracy_vs_threshold.png"), dpi=220); plt.close()

    fig, ax = plt.subplots(1, 2, figsize=(20, 7.6))                                     # Figure 8
    share = [stats[f"gate.{c}"]["share"] * 100 for c in CONDITIONS]
    bars = ax[0].bar(["clean", "obfuscated"], share, color=["#1db07c", "#c88500"], width=0.55)
    for bar, v, c in zip(bars, share, CONDITIONS):
        ax[0].text(bar.get_x() + bar.get_width() / 2, v + 0.6, f"{v:.1f}% ({stats[f'gate.{c}']['n']} of 1,000)",
                   ha="center", fontsize=13)
    ax[0].set_ylim(0, max(share) * 1.25); ax[0].set_ylabel("Contracts where the gate opened (%)")
    ax[0].set_title("(a) How often W2/W3 are consulted", fontsize=17)
    labels8 = ["CodeBERT\nonly", "Forta\nonly", "CRP\nonly", "Exactly two\ncorrect", "All three\ncorrect", "All three\nwrong"]
    vals = [unique[k] for k in ("codebert_only", "forta_only", "crpwarner_only", "exactly_two", "all_three", "none")]
    bars = ax[1].bar(labels8, vals, color=["#1db07c", "#2a78d6", "#e8673a", "#b9b9b4", "#8f8f8a", "#d64545"])
    for bar, v in zip(bars, vals):
        ax[1].text(bar.get_x() + bar.get_width() / 2, v + 6, str(v), ha="center", fontsize=13)
    ax[1].set_ylabel("Number of contract evaluations\n(both conditions, n = 2,000)")
    ax[1].set_title("(b) Which modalities were correct", fontsize=17); ax[1].tick_params(axis="x", labelsize=11.5)
    plt.tight_layout(); plt.savefig(os.path.join(fig_dir, "Figure8_modality_contribution.png"), dpi=220); plt.close()
    print(f"Wrote table2.csv, table2.tex, stats.json and figures to {args.out}")


if __name__ == "__main__":
    main()
