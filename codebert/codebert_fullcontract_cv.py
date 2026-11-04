# =====================================================================
# Rug-Pull Defender: CodeBERT on the FULL contract, 5-fold cross-validation
# ---------------------------------------------------------------------
# What this script does
#   1. Splits every flattened file into its top-level blocks
#      (contract / library / interface).
#   2. Removes only blocks that carry no project-specific logic:
#        - interfaces (they have no function bodies), and
#        - library/contract blocks whose code, after comments and
#          whitespace are stripped, appears IDENTICALLY in at least
#          MIN_DUP different files of the dataset (standard copies such as
#          SafeMath, Context, Ownable, ERC20 from OpenZeppelin).
#      A copy that differs by even one token is KEPT, so tampered
#      libraries stay visible. The last contract of the file (the main
#      contract) is never removed. No labels are used in this step.
#      The same blocks are removed from the obfuscated version.
#   3. Tokenizes the remaining source WITHOUT truncation and splits it into
#      overlapping 512-token windows (stride 256). CodeBERT sees every window.
#   4. Runs stratified 5-fold cross-validation over all 1,000 contracts.
#      In each fold, 10% of the training part is held out (inner_val) for
#      early stopping. Every contract therefore receives exactly one
#      out-of-fold prediction, for the clean and for the obfuscated source.
#   5. Aggregates window probabilities per contract in three ways
#      (max, mean, mean of the top 3). The choice between them is made
#      later on the inner_val rows, never on the test rows.
#
# Inputs (upload to /content before running):
#   dataset.xlsx
#   flatten_source_code_noheader.zip
#   obfuscated_contracts_noheader.zip
#
# Runtime: Runtime -> Change runtime type -> T4 GPU   (do NOT run on CPU)
# Expected time on a T4: roughly 4 to 6 hours in total (full mode, then the short tail baseline).
# Both input modes (full, then tail) run in one go; the tail baseline adds well under an hour.
# Outputs are written to Google Drive after EVERY fold, so a disconnect
# loses at most the fold that was running. Re-running skips finished folds.
# =====================================================================

import os, re, io, json, time, zipfile, random, hashlib
from collections import Counter
import numpy as np, pandas as pd
import torch, torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModel
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score

# ---------------- settings ----------------
INPUT_MODES  = ["full", "tail"]  # "full" = whole contract in windows (main run); "tail" = last 512 tokens of the raw file (baseline, same folds)
SEEDS        = [42]       # one seed per fold keeps the run within a Colab session; add more if time allows
N_FOLDS      = 5
MIN_DUP      = 5          # a block is "standard" if its normalized code appears identically in >= MIN_DUP files
WIN, STRIDE  = 512, 256
MAX_WIN_TRAIN = 16        # cap on windows per contract during training (evenly spaced); inference uses all windows
MAX_WIN_INFER = 96
BATCH_SIZE   = 8
EPOCHS       = 8
PATIENCE     = 3
LR           = 2e-5
DATA_DIR     = os.environ.get("RPD_DATA_DIR", "/content")       # folder with the three input files
USE_DRIVE    = os.environ.get("RPD_USE_DRIVE", "1") == "1"    # save outputs to Google Drive (Colab)

if USE_DRIVE:
    from google.colab import drive
    drive.mount("/content/drive")
    BASE_DIR = "/content/drive/MyDrive/rugpull_defender_fullcv"
else:
    BASE_DIR = os.environ.get("RPD_OUT_DIR", "rugpull_defender_fullcv")
os.makedirs(BASE_DIR, exist_ok=True)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
assert device.type == "cuda", "No GPU found. Switch the runtime to T4 GPU before running."
print("device:", device, "| output:", BASE_DIR)

# ---------------- data ----------------
df = pd.read_excel(f"{DATA_DIR}/dataset.xlsx")
df["number"] = range(1, len(df) + 1)
df["y"] = (df["class"].astype(str).str.lower() == "scam").astype(int)

def read_zip(path):
    z = zipfile.ZipFile(path); out = {}
    for n in z.namelist():
        m = re.search(r"(\d+)\.txt$", n)
        if m: out[int(m.group(1))] = z.read(n).decode("utf8", "ignore")
    return out
SRC = {"clean": read_zip(f"{DATA_DIR}/flatten_source_code_noheader.zip"),
       "obfuscated": read_zip(f"{DATA_DIR}/obfuscated_contracts_noheader.zip")}
df = df[df.number.isin(SRC["clean"].keys())].reset_index(drop=True)
print("contracts:", len(df), "| scam:", int(df.y.sum()), "| normal:", int((1 - df.y).sum()))

# ---------------- block segmentation ----------------
def mask_comments_strings(code):
    """Same-length copy in which comments and string literals are blanked, so braces inside them are ignored."""
    out = list(code); i, n = 0, len(code)
    while i < n:
        c = code[i]; nx = code[i + 1] if i + 1 < n else ""
        if c == "/" and nx == "/":
            j = code.find("\n", i); j = n if j < 0 else j
            for k in range(i, j): out[k] = " "
            i = j
        elif c == "/" and nx == "*":
            j = code.find("*/", i + 2); j = n if j < 0 else j + 2
            for k in range(i, j):
                if code[k] != "\n": out[k] = " "
            i = j
        elif c in "\"'":
            q = c; j = i + 1
            while j < n and code[j] != q:
                j += 2 if code[j] == "\\" else 1
            j = min(j + 1, n)
            for k in range(i + 1, j - 1): out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)

DECL = re.compile(r"\b(?:abstract\s+)?(contract|library|interface)\s+([A-Za-z_$][\w$]*)")
def blocks(code):
    """List of (kind, start, end) for top-level declarations, using brace matching on the masked text."""
    m = mask_comments_strings(code); res = []; pos = 0; depth = 0
    for mt in DECL.finditer(m):
        if mt.start() < pos: continue
        depth += m.count("{", pos, mt.start()) - m.count("}", pos, mt.start()); pos = mt.start()
        if depth != 0: continue
        ob = m.find("{", mt.end())
        if ob < 0: break
        d = 0; k = ob
        while k < len(m):
            if m[k] == "{": d += 1
            elif m[k] == "}":
                d -= 1
                if d == 0: break
            k += 1
        res.append((mt.group(1), mt.start(), k + 1)); pos = k + 1; depth = 0
    return res

def normalize(txt):
    m = mask_comments_strings(txt)
    return re.sub(r"\s+", " ", m).strip()

blk = {cond: {n: blocks(SRC[cond][n]) for n in df.number} for cond in SRC}
norm_count = Counter()
for n in df.number:
    seen = set()
    for kind, s, e in blk["clean"][n]:
        h = hashlib.sha1(normalize(SRC["clean"][n][s:e]).encode()).hexdigest()
        if h not in seen: norm_count[h] += 1; seen.add(h)

PRE = {"clean": {}, "obfuscated": {}}; stats = []
for n in df.number:
    bc = blk["clean"][n]; drop = set()
    last_contract = max([i for i, (k, s, e) in enumerate(bc) if k == "contract"], default=len(bc) - 1)
    for i, (kind, s, e) in enumerate(bc):
        if i == last_contract: continue
        if kind == "interface": drop.add(i); continue
        h = hashlib.sha1(normalize(SRC["clean"][n][s:e]).encode()).hexdigest()
        if norm_count[h] >= MIN_DUP: drop.add(i)
    aligned = True
    for cond in ("clean", "obfuscated"):
        code = SRC[cond][n]; b = blk[cond][n]
        if cond == "obfuscated" and len(b) != len(bc):
            aligned = False; PRE[cond][n] = code; continue
        keep, last = [], 0
        for i, (kind, s, e) in enumerate(b):
            keep.append(code[last:s])
            if i not in drop: keep.append(code[s:e])
            last = e
        keep.append(code[last:]); PRE[cond][n] = "".join(keep)
    stats.append(dict(number=n, blocks=len(bc), dropped=len(drop), chars_before=len(SRC["clean"][n]),
                      chars_after=len(PRE["clean"][n]), obf_aligned=aligned))
ST = pd.DataFrame(stats)
print("blocks dropped (median per file):", ST.dropped.median(), "| chars kept (median share):",
      round((ST.chars_after / ST.chars_before).median(), 3), "| obfuscated aligned:", ST.obf_aligned.mean().round(3))

ALL_ZIPS = []
for INPUT_MODE in INPUT_MODES:
    OUT_DIR = f"{BASE_DIR}/{INPUT_MODE}"; os.makedirs(OUT_DIR, exist_ok=True)
    print("\n" + "=" * 60 + f"\nINPUT MODE: {INPUT_MODE}\n" + "=" * 60)
    # ---------------- tokenization into windows ----------------
    tokenizer = AutoTokenizer.from_pretrained("microsoft/codebert-base")
    CLS, SEP, PAD = tokenizer.cls_token_id, tokenizer.sep_token_id, tokenizer.pad_token_id
    BODY = WIN - 2
    def windows(text):
        ids = tokenizer(text, add_special_tokens=False, truncation=False)["input_ids"]
        if INPUT_MODE == "tail":
            ids = ids[-BODY:]; starts = [0]
        else:
            starts = list(range(0, max(1, len(ids) - BODY + STRIDE), STRIDE)) if len(ids) > BODY else [0]
        out = []
        for s in starts:
            w = [CLS] + ids[s:s + BODY] + [SEP]
            out.append(w + [PAD] * (WIN - len(w)))
        return out, len(ids)

    WINS = {"clean": {}, "obfuscated": {}}; ntok = {}
    t0 = time.time()
    for cond in WINS:
        for n in df.number:
            w, L = windows(SRC[cond][n] if INPUT_MODE == "tail" else PRE[cond][n]); WINS[cond][n] = w
            if cond == "clean": ntok[n] = L
    ST["tokens"] = ST.number.map(ntok); ST["windows"] = ST.number.map(lambda n: len(WINS["clean"][n]))
    ST.to_csv(f"{OUT_DIR}/preprocessing_stats.csv", index=False)
    print(f"tokenized in {time.time()-t0:.0f}s | tokens median {ST.tokens.median():.0f} | windows median {ST.windows.median():.0f}, max {ST.windows.max()}")

    def spaced(lst, k):
        if len(lst) <= k: return lst
        idx = np.linspace(0, len(lst) - 1, k).round().astype(int); return [lst[i] for i in idx]

    class WinDS(Dataset):
        def __init__(self, numbers, cond, train):
            self.rows = []
            for n in numbers:
                ws = WINS[cond][n]
                ws = spaced(ws, MAX_WIN_TRAIN) if train else spaced(ws, MAX_WIN_INFER)
                for w in ws: self.rows.append((n, w, 1.0 / len(ws)))
        def __len__(self): return len(self.rows)
        def __getitem__(self, i):
            n, w, wt = self.rows[i]; ids = torch.tensor(w)
            return dict(number=n, input_ids=ids, attention_mask=(ids != PAD).long(), weight=torch.tensor(wt, dtype=torch.float))

    class CodeBERTClassifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = AutoModel.from_pretrained("microsoft/codebert-base")
            self.dropout = nn.Dropout(0.1); self.classifier = nn.Linear(self.encoder.config.hidden_size, 2)
        def forward(self, input_ids, attention_mask):
            h = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            m = attention_mask.unsqueeze(-1).float(); pooled = (h * m).sum(1) / m.sum(1).clamp(min=1)
            return self.classifier(self.dropout(pooled))

    @torch.no_grad()
    def predict(model, numbers, cond):
        model.eval(); ds = WinDS(numbers, cond, train=False)
        dl = DataLoader(ds, batch_size=BATCH_SIZE * 2, shuffle=False)
        per = {}
        for b in dl:
            with torch.autocast("cuda", dtype=torch.float16):
                lg = model(b["input_ids"].to(device), b["attention_mask"].to(device))
            p = torch.softmax(lg.float(), 1)[:, 1].cpu().numpy()
            for n, pp in zip(b["number"].tolist(), p): per.setdefault(n, []).append(float(pp))
        out = {}
        for n, ps in per.items():
            ps = np.array(ps); top = np.sort(ps)[-3:]
            out[n] = dict(p_max=ps.max(), p_mean=ps.mean(), p_top3=top.mean(), n_windows=len(ps))
        return out

    # ---------------- cross-validation ----------------
    Y = df.set_index("number").y
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
    folds = list(skf.split(df.number, df.y))
    json.dump({int(n): int(k) for k, (_, te) in enumerate(folds) for n in df.number.iloc[te]},
              open(f"{OUT_DIR}/fold_assignment.json", "w"))
    pred_path, log_path = f"{OUT_DIR}/codebert_fullcv_probs.csv", f"{OUT_DIR}/training_log.csv"
    done = set()
    if os.path.exists(pred_path):
        old = pd.read_csv(pred_path); done = set(zip(old.seed, old.fold))
        print("already finished (seed, fold):", sorted(done))

    for seed in SEEDS:
        for k, (tr_idx, te_idx) in enumerate(folds):
            if (seed, k) in done: continue
            t_fold = time.time()
            random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True; torch.backends.cudnn.benchmark = False
            tr_all = df.number.iloc[tr_idx].values; te = df.number.iloc[te_idx].values
            tr, va = train_test_split(tr_all, test_size=0.10, stratify=Y.loc[tr_all].values, random_state=seed)
            model = CodeBERTClassifier().to(device)
            opt = torch.optim.AdamW(model.parameters(), lr=LR)
            scaler = torch.cuda.amp.GradScaler()
            ce = nn.CrossEntropyLoss(reduction="none")
            dl = DataLoader(WinDS(tr, "clean", train=True), batch_size=BATCH_SIZE, shuffle=True)
            best, best_state, wait, logs = 1e9, None, PATIENCE, []
            for ep in range(1, EPOCHS + 1):
                model.train(); tot = 0.0
                for b in dl:
                    y = torch.tensor([int(Y[n]) for n in b["number"].tolist()], device=device)
                    with torch.autocast("cuda", dtype=torch.float16):
                        lg = model(b["input_ids"].to(device), b["attention_mask"].to(device))
                    w = b["weight"].to(device); loss = (ce(lg.float(), y) * w).sum() / w.sum()
                    opt.zero_grad(); scaler.scale(loss).backward(); scaler.step(opt); scaler.update(); tot += loss.item()
                pv = predict(model, va, "clean"); yv = Y.loc[va].values
                pm = np.clip(np.array([pv[n]["p_mean"] for n in va]), 1e-6, 1 - 1e-6)
                vloss = float(-(yv * np.log(pm) + (1 - yv) * np.log(1 - pm)).mean())
                vacc = {a: accuracy_score(yv, np.array([pv[n][a] for n in va]) >= 0.5) for a in ("p_max", "p_mean", "p_top3")}
                logs.append(dict(seed=seed, fold=k, epoch=ep, train_loss=tot / len(dl), val_logloss_mean=vloss, **{f"val_acc_{a}": v for a, v in vacc.items()}))
                print(f"seed {seed} fold {k} epoch {ep}: train {tot/len(dl):.4f} | val logloss {vloss:.4f} | val acc max/mean/top3 "
                      f"{vacc['p_max']:.3f}/{vacc['p_mean']:.3f}/{vacc['p_top3']:.3f}")
                if vloss < best:
                    best, wait = vloss, PATIENCE; best_state = {kk: v.detach().cpu().clone() for kk, v in model.state_dict().items()}
                else:
                    wait -= 1
                    if wait == 0: print("early stopping"); break
            model.load_state_dict(best_state)
            torch.save({kk: (v.half() if v.is_floating_point() else v) for kk, v in best_state.items()},
                       f"{OUT_DIR}/codebert_{INPUT_MODE}_fold{k}_seed{seed}.pt")
            rows = []
            for split, nums, conds in (("inner_val", va, ("clean",)), ("test", te, ("clean", "obfuscated"))):
                for cond in conds:
                    P = predict(model, nums, cond)
                    for n in nums:
                        rows.append(dict(seed=seed, fold=k, number=int(n), split=split, condition=cond, y=int(Y[n]), **P[n]))
            R = pd.DataFrame(rows)
            R.to_csv(pred_path, mode="a", header=not os.path.exists(pred_path), index=False)
            pd.DataFrame(logs).to_csv(log_path, mode="a", header=not os.path.exists(log_path), index=False)
            T = R[(R.split == "test")]
            for cond in ("clean", "obfuscated"):
                t = T[T.condition == cond]
                print(f"  fold {k} {cond}: acc(max) {accuracy_score(t.y, t.p_max>=0.5):.3f} acc(mean) {accuracy_score(t.y, t.p_mean>=0.5):.3f} "
                      f"AUC(mean) {roc_auc_score(t.y, t.p_mean):.3f}")
            print(f"fold {k} finished in {(time.time()-t_fold)/60:.1f} min")
            del model, opt; torch.cuda.empty_cache()

    # ---------------- package ----------------
    zp = f"/content/codebert_fullcv_{INPUT_MODE}_results.zip"; ALL_ZIPS.append(zp)
    with zipfile.ZipFile(zp, "w") as z:
        for f in ("codebert_fullcv_probs.csv", "training_log.csv", "preprocessing_stats.csv", "fold_assignment.json"):
            if os.path.exists(f"{OUT_DIR}/{f}"): z.write(f"{OUT_DIR}/{f}", f)
    print("results zip:", zp, "(also in Drive:", OUT_DIR, ")")

# ---------------- one zip with everything ----------------
zp_all = "/content/codebert_fullcv_ALL_results.zip"
with zipfile.ZipFile(zp_all, "w") as z:
    for m in INPUT_MODES:
        for f in ("codebert_fullcv_probs.csv", "training_log.csv", "preprocessing_stats.csv", "fold_assignment.json"):
            p = f"{BASE_DIR}/{m}/{f}"
            if os.path.exists(p): z.write(p, f"{m}/{f}")
print("ALL DONE. Send this file:", zp_all)
try:
    from google.colab import files; files.download(zp_all)
except Exception as e:
    print("download manually from the Files panel or from Drive:", BASE_DIR, e)
