#!/usr/bin/env python3
"""
Template reuse across cross-validation folds (Section 7, third limitation).

For every contract, the project-specific code is obtained exactly as for the
CodeBERT input (codebert/codebert_fullcontract_cv.py): interfaces and library or
contract blocks that appear identically in at least five files are removed, and
the main contract is always kept. Each contract is then represented by a
MinHash of its comment-free 5-token shingles. A contract counts as having a
near-duplicate when some contract in a different fold has an estimated Jaccard
similarity of at least 0.9.

Usage (from the repository root):
    python cascade/near_duplicates.py

Output:
    results/near_duplicates.pkl   list of contract ids with a cross-fold near-duplicate
    (cascade/evaluate.py reads this file to report accuracy on the remaining contracts)
"""

import hashlib
import json
import os
import pickle
import re
import zipfile
from collections import Counter

import numpy as np
import pandas as pd
from datasketch import MinHash, MinHashLSH

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


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



def strip_comments(code):
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return re.sub(r"//[^\n]*", "", code)


def shingles(code, k=5):
    tokens = re.findall(r"[A-Za-z_]\w*|\d+|[^\s\w]", strip_comments(code))
    return {" ".join(tokens[i:i + k]) for i in range(max(1, len(tokens) - k + 1))}


def main():
    with zipfile.ZipFile(os.path.join(DATA, "flatten_source_code_noheader.zip")) as z:
        src = {int(re.search(r"(\d+)\.txt$", n).group(1)): z.read(n).decode("utf8", "ignore")
               for n in z.namelist() if n.endswith(".txt")}
    nums = sorted(src)
    blk = {n: blocks(src[n]) for n in nums}
    counts = Counter()
    for n in nums:
        seen = set()
        for _, a, b in blk[n]:
            h = hashlib.sha1(normalize(src[n][a:b]).encode()).hexdigest()
            if h not in seen:
                counts[h] += 1
                seen.add(h)
    project_code = {}
    for n in nums:
        bc = blk[n]
        last = max([i for i, (kind, _, _) in enumerate(bc) if kind == "contract"], default=len(bc) - 1)
        keep, pos = [], 0
        for i, (kind, a, b) in enumerate(bc):
            keep.append(src[n][pos:a])
            h = hashlib.sha1(normalize(src[n][a:b]).encode()).hexdigest()
            if i == last or not (kind == "interface" or counts[h] >= 5):
                keep.append(src[n][a:b])
            pos = b
        keep.append(src[n][pos:])
        project_code[n] = "".join(keep)

    fold = {int(k): v for k, v in json.load(open(os.path.join(DATA, "fold_assignment.json"))).items()}
    meta = pd.read_excel(os.path.join(DATA, "dataset.xlsx"))
    label = {i + 1: int(c == "scam") for i, c in enumerate(meta["class"])}
    mh = {}
    for n in nums:
        m = MinHash(num_perm=128, seed=1)
        for s in shingles(project_code[n]):
            m.update(s.encode())
        mh[n] = m
    lsh = MinHashLSH(threshold=0.85, num_perm=128)
    for n in nums:
        lsh.insert(str(n), mh[n])
    dup, same_label = [], 0
    for n in nums:
        near = [int(x) for x in lsh.query(mh[n])
                if int(x) != n and fold[int(x)] != fold[n] and mh[n].jaccard(mh[int(x)]) >= 0.9]
        if near:
            dup.append(n)
            same_label += any(label[x] == label[n] for x in near)
    print(f"contracts with a cross-fold near-duplicate: {len(dup)} ({len(dup) / len(nums):.1%}); "
          f"same label as a neighbour: {same_label / max(1, len(dup)):.0%}")
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    pickle.dump(dup, open(os.path.join(ROOT, "results", "near_duplicates.pkl"), "wb"))


if __name__ == "__main__":
    main()
