#!/usr/bin/env python3
"""
Compile the main contract of every project to runtime bytecode for CRPWarner.

CRPWarner analyzes EVM runtime bytecode, and each flattened file usually holds
several contracts (the token itself plus libraries such as SafeMath). Running
the tool on the wrong contract silently produces meaningless flags, so this
script selects the main contract explicitly:

  * candidates are the concrete (non-abstract) contracts that no other contract
    in the same file inherits from;
  * among the candidates that compile, the one with the largest runtime
    bytecode is taken as the main contract.

Compiler choice: the newest solc release up to 0.8.19 that satisfies all
version pragmas of the original (clean) file is tried first, so that the
bytecode contains no PUSH0 opcode, which older analysis back-ends cannot
decode. For solc >= 0.8.7 the London EVM version is set explicitly. If no
pragma-compatible release compiles the file, the pragmas are removed and a
fixed list of common releases is tried ("pragma relaxed" in the log).

The renamed (obfuscated) file of each project is compiled with the same
procedure, and its main contract is selected by the same rule.

Static solc binaries are downloaded once from the official GitHub releases.

Usage:
    python prepare_bytecode.py --clean ../data/flatten_source_code_noheader.zip \
        --obfuscated ../data/obfuscated_contracts_noheader.zip --out bytecode/

Output:
    <out>/clean/<id>.hex, <out>/obfuscated/<id>.hex    runtime bytecode
    <out>/log_clean.csv, <out>/log_obfuscated.csv       compiler and main contract per project
"""

import argparse
import json
import os
import re
import subprocess
import urllib.request
import zipfile
from concurrent.futures import ProcessPoolExecutor

import pandas as pd
import semantic_version as sv

VERSIONS = ([f"0.4.{i}" for i in range(11, 27)] + [f"0.5.{i}" for i in range(0, 18)] +
            [f"0.6.{i}" for i in range(0, 13)] + [f"0.7.{i}" for i in range(0, 7)] +
            [f"0.8.{i}" for i in range(0, 29)])
VERSIONS = [sv.Version(v) for v in VERSIONS]
FALLBACK = ["0.4.26", "0.4.24", "0.4.18", "0.5.17", "0.5.16", "0.6.12", "0.7.6", "0.8.19", "0.8.4", "0.4.11"]
DECL = re.compile(r"^\s*(abstract\s+contract|contract|library|interface)\s+(\w+)([^{]*)\{", re.M)
SOLC_DIR = "solc_bin"


def get_solc(version: str) -> str:
    """Path to a static solc binary, downloading it on first use."""
    os.makedirs(SOLC_DIR, exist_ok=True)
    path = os.path.join(SOLC_DIR, f"solc-{version}")
    if not os.path.exists(path):
        url = f"https://github.com/ethereum/solidity/releases/download/v{version}/solc-static-linux"
        urllib.request.urlretrieve(url, path)
        os.chmod(path, 0o755)
    return path


def candidate_versions(source: str) -> list:
    """Releases that satisfy every version pragma, pre-PUSH0 releases first."""
    ok = list(VERSIONS)
    for spec in re.findall(r"pragma\s+solidity\s+([^;]+);", source):
        try:
            npm = sv.NpmSpec(re.sub(r"\s+", " ", spec.strip()))
            ok = [v for v in ok if v in npm]
        except ValueError:
            pass
    ok.sort(reverse=True)
    early = [v for v in ok if v <= sv.Version("0.8.19")]
    late = [v for v in ok if v > sv.Version("0.8.19")]
    return [str(v) for v in early + late]


def strip_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return re.sub(r"//[^\n]*", "", code)


def leaf_contracts(code: str):
    """Concrete contracts that no other contract in the file inherits from."""
    decls = [(m.group(1), m.group(2), m.group(3)) for m in DECL.finditer(strip_comments(code))]
    concrete = [name for kind, name, _ in decls if kind == "contract"]
    bases = set()
    for _, _, rest in decls:
        inherit = re.search(r"\bis\b(.*)", rest, re.S)
        if inherit:
            bases |= set(re.findall(r"\b(\w+)\b", re.sub(r"\([^)]*\)", "", inherit.group(1))))
    return [n for n in concrete if n not in bases], concrete


def run_solc(version: str, path: str):
    """Compile with one release; return {contract: runtime bytecode} or None."""
    evm = ["--evm-version", "london"] if sv.Version(version) >= sv.Version("0.8.7") else []
    for extra in ([], ["--optimize"]):
        try:
            res = subprocess.run([get_solc(version), "--combined-json", "bin-runtime"] + evm + extra + [path],
                                 capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            continue
        if res.returncode == 0 and res.stdout.strip():
            try:
                contracts = json.loads(res.stdout)["contracts"]
                return {k.split(":")[-1]: v["bin-runtime"] for k, v in contracts.items()}
            except (KeyError, ValueError):
                pass
    return None


def compile_project(job):
    cond, gid, source, clean_source, out_dir = job
    tmp = f"/tmp/rpd_{cond}_{gid}.sol"
    record = dict(GroupID=gid, solc=None, main=None, bytes=None, candidates=None)
    bins = None
    with open(tmp, "w") as fh:
        fh.write(source)
    for version in candidate_versions(clean_source)[:3]:
        bins = run_solc(version, tmp)
        if bins:
            record["solc"] = version
            break
    if not bins:                                   # conflicting or unsupported pragmas
        with open(tmp, "w") as fh:
            fh.write(re.sub(r"pragma\s+solidity[^;]*;", "", source))
        for version in FALLBACK:
            bins = run_solc(version, tmp)
            if bins:
                record["solc"] = version + " (pragma relaxed)"
                break
    if bins:
        leaves, concrete = leaf_contracts(source)
        cands = [(n, bins[n]) for n in leaves if bins.get(n)] or \
                [(n, b) for n, b in bins.items() if b and n in concrete]
        if cands:
            name, code = max(cands, key=lambda t: len(t[1]))
            with open(os.path.join(out_dir, cond, f"{gid}.hex"), "w") as fh:
                fh.write(code)
            record.update(main=name, bytes=len(code) // 2, candidates="|".join(n for n, _ in cands))
    os.remove(tmp)
    return record


def read_zip(path: str) -> dict:
    with zipfile.ZipFile(path) as z:
        return {int(re.search(r"(\d+)\.txt$", n).group(1)): z.read(n).decode("utf-8", "ignore")
                for n in z.namelist() if n.endswith(".txt")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clean", required=True, help="zip with the original flattened sources")
    ap.add_argument("--obfuscated", required=True, help="zip with the renamed sources")
    ap.add_argument("--out", default="bytecode")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    args = ap.parse_args()

    clean = read_zip(args.clean)
    sources = {"clean": clean, "obfuscated": read_zip(args.obfuscated)}
    for v in sorted({v for s in clean.values() for v in candidate_versions(s)[:3]} | set(FALLBACK)):
        get_solc(v)                                # download sequentially before the parallel run
    for cond in ("clean", "obfuscated"):
        os.makedirs(os.path.join(args.out, cond), exist_ok=True)
        jobs = [(cond, g, sources[cond][g], clean[g], args.out) for g in sorted(sources[cond])]
        with ProcessPoolExecutor(args.jobs) as pool:
            log = pd.DataFrame(list(pool.map(compile_project, jobs)))
        log.to_csv(os.path.join(args.out, f"log_{cond}.csv"), index=False)
        print(f"{cond}: {log.main.notna().sum()} of {len(log)} projects produced bytecode")


if __name__ == "__main__":
    main()
