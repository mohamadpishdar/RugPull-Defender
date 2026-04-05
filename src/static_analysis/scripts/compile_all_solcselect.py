#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch-compile Solidity sources from dataset/sourse_code/ into dataset/bytecode_compile_all_solcselect/<id>/

ALWAYS uses solc-select (for 0.4.x, 0.5.x, 0.6.x, 0.7.x, 0.8.x).
If a required version is not installed, the script will install it via solc-select.

Outputs per file:
  *.bin           (creation bytecode)
  *.bin-runtime   (runtime bytecode)
  *.hex           (runtime bytecode, 0x-prefixed)
Plus a per-file compile_summary.json and a batch CSV.

Usage:
  python3 compile_all_solcselect.py [--auto-npm] [--dry-run]
"""

import csv
import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Optional
from packaging import specifiers, version

ROOT = Path("/home/senatoma/coinfa/RugPullHunter").resolve()
DATASET = ROOT / "dataset"
SRC_DIR = DATASET / "source_code"
OUT_DIR = DATASET / "bytecode_compile_all_solcselect"

# Comprehensive list of stable Solidity releases
STABLE_VERSIONS = [
    "0.4.0", "0.4.1", "0.4.2", "0.4.3", "0.4.4", "0.4.5", "0.4.6", "0.4.7", "0.4.8", "0.4.9",
    "0.4.10", "0.4.11", "0.4.12", "0.4.13", "0.4.14", "0.4.15", "0.4.16", "0.4.17", "0.4.18",
    "0.4.19", "0.4.20", "0.4.21", "0.4.22", "0.4.23", "0.4.24", "0.4.25", "0.4.26",
    "0.5.0", "0.5.1", "0.5.2", "0.5.3", "0.5.4", "0.5.5", "0.5.6", "0.5.7", "0.5.8", "0.5.9",
    "0.5.10", "0.5.11", "0.5.12", "0.5.13", "0.5.14", "0.5.15", "0.5.16", "0.5.17",
    "0.6.0", "0.6.1", "0.6.2", "0.6.3", "0.6.4", "0.6.5", "0.6.6", "0.6.7", "0.6.8", "0.6.9",
    "0.6.10", "0.6.11", "0.6.12",
    "0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4", "0.7.5", "0.7.6",
    "0.8.0", "0.8.1", "0.8.2", "0.8.3", "0.8.4", "0.8.5", "0.8.6", "0.8.7", "0.8.8", "0.8.9",
    "0.8.10", "0.8.11", "0.8.12", "0.8.13", "0.8.14", "0.8.15", "0.8.16", "0.8.17", "0.8.18",
    "0.8.19", "0.8.20", "0.8.21", "0.8.22", "0.8.23", "0.8.24", "0.8.25", "0.8.26", "0.8.27",
    "0.8.28", "0.8.29", "0.8.30"
]

SOLC_SELECT = Path.home() / ".local/bin/solc-select"
NPM_HINTS = [
    "@openzeppelin/contracts",
    "@uniswap/v2-core",
    "@uniswap/v2-periphery",
]

def run(cmd, cwd=None, check=True):
    proc = subprocess.Popen(
        cmd if isinstance(cmd, list) else shlex.split(cmd),
        cwd=str(cwd) if cwd else None,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    out, err = proc.communicate()
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {cmd}\n{err}")
    return proc.returncode, out, err

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")

def extract_pragma_expression(text: str) -> Optional[str]:
    """Extract the version expression from pragma solidity statement."""
    match = re.search(r"pragma\s+solidity\s+([^;]+);", text)
    return match.group(1).strip() if match else None

def convert_solidity_to_pep440(expr: str) -> str:
    """
    Convert Solidity version syntax to PEP 440 specifier format.
    
    Solidity uses ^ for compatible versions (like ~= in PEP 440).
    PEP 440 requires commas between multiple specifiers.
    """
    # Handle caret (^) - convert to ~= (compatible release)
    if expr.startswith("^"):
        return expr.replace("^", "~=")
    
    # Handle single equal sign (=) - convert to == for PEP 440
    if expr.startswith("=") and len(expr) > 1 and expr[1].isdigit():
        return f"={expr}"
    
    # Handle plain version (no operator) - treat as exact match
    if expr[0].isdigit():
        return f"=={expr}"
    
    # Handle range with spaces - convert to comma-separated format
    # Example: ">=0.4.22 <0.6.0" -> ">=0.4.22,<0.6.0"
    if " " in expr:
        return expr.replace(" ", ",")
    
    # Already has operator (>=, ==, <, etc.)
    return expr

def get_latest_matching_version(version_spec: str) -> Optional[str]:
    """
    Get the latest stable version matching the given specifier.
    
    Uses the packaging library for proper semantic version matching.
    """
    try:
        spec = specifiers.SpecifierSet(version_spec)
        
        # Filter stable versions that match the specifier
        matching_versions = [
            v for v in STABLE_VERSIONS 
            if version.Version(v) in spec
        ]
        
        if not matching_versions:
            return None
        
        # Return the latest matching version
        return str(max(matching_versions, key=lambda v: version.Version(v)))
    
    except Exception:
        return None
    
def detect_solc_version(text: str) -> str:
    """
    Detect the exact solc-select version from Solidity pragma.
    
    Returns:
        - Latest stable patch for ^ (e.g., "0.8.30" for "^0.8.4")
        - Exact stable patch for = or plain version (e.g., "0.5.11" for "0.5.11")
        - Latest version matching >= (e.g., "0.5.17" for ">=0.5.17")
        - Latest stable patch for ranges (e.g., "0.5.17" for ">=0.4.22 <0.6.0")
        - Empty string if not found
    """
    # Extract the version expression from pragma
    expr = extract_pragma_expression(text)
    if not expr:
        return ""
    
    # Convert Solidity syntax to PEP 440 format
    pep440_spec = convert_solidity_to_pep440(expr)
    
    # Get the latest matching version
    result = get_latest_matching_version(pep440_spec)
    return result if result else ""

def ensure_solc(version:str):
    if not SOLC_SELECT.exists():
        raise SystemExit("solc-select not found at ~/.local/bin/solc-select")
    # install if missing
    _, out, _ = run([str(SOLC_SELECT),"versions"], check=False)
    if version not in out:
        print(f"[solc-select] install {version}")
        run([str(SOLC_SELECT),"install",version])
    print(f"[solc-select] use {version}")
    run([str(SOLC_SELECT),"use",version])

def solc_supports(opt:str)->bool:
    rc, out, _ = run("solc --help", check=False)
    return (opt in out)

def needs_npm_imports(text: str) -> bool:
    return any(x in text for x in NPM_HINTS)

def ensure_node_modules():
    if not (ROOT/"node_modules").exists():
        print("[npm] bootstrapping node_modules (OZ + Uniswap)…")
        run("npm init -y", cwd=ROOT)
        run(["npm", "i",
         "@openzeppelin/contracts@^4",
         "@uniswap/v2-core",
         "@uniswap/v2-periphery"], cwd=ROOT)

def ensure_symlink(name:str, target:Path):
    link = ROOT/name
    if link.exists() or link.is_symlink(): return
    if target.exists():
        print(f"[link] {name} -> {target}")
        link.symlink_to(target, target_is_directory=True)

def prepare_npm_resolution(current_solc_supports_include:bool):
    """If solc lacks --include-path, create @org symlinks so imports resolve."""
    if current_solc_supports_include: 
        return
    ensure_node_modules()
    ensure_symlink("@openzeppelin", ROOT/"node_modules/@openzeppelin")
    ensure_symlink("@uniswap", ROOT/"node_modules/@uniswap")

def compile_one(src: Path, out_dir: Path, detected_version: str):
    """
    Compile a single Solidity source file.
    
    Args:
        src: Path to source file
        out_dir: Output directory for compiled artifacts
        detected_version: The detected version from pragma (e.g., "0.8.30")
    """
    # Use the detected version, or fall back to latest if detection failed
    if not detected_version or detected_version == "(none)":
        print(f"[warn] No valid pragma found in {src.name}, using latest version")
        version = STABLE_VERSIONS[-1]
    else:
        version = detected_version

    print(f"[info] Detected version for {src.name}: {version}")
    ensure_solc(version)

    # Detect support
    has_base     = solc_supports("--base-path")
    has_include  = solc_supports("--include-path")
    has_allow    = solc_supports("--allow-paths")

    txt = read(src)
    if needs_npm_imports(txt):
        prepare_npm_resolution(has_include)

    args = ["solc","--bin","--bin-runtime","-o",str(out_dir),"--overwrite",str(src)]

    if has_base:    args[0:0] = []  # no need to add first; we just append
    if has_base:    args.extend(["--base-path", str(ROOT)])
    if has_include: args.extend(["--include-path", str(ROOT/"node_modules")])
    if has_allow:   args.extend(["--allow-paths", f"{ROOT},{ROOT/'node_modules'}"])

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[compile] {src.name} (solc {version}) → {out_dir}")
    rc,out,err = run(args, check=False)
    if rc!=0:
        (out_dir/"compile.stderr").write_text(err)
        print(f"[error] solc failed for {src.name}; see {out_dir/'compile.stderr'}")
        return {"ok":False,"version":version,"hexes":[]}

    # make 0x-hex alongside each runtime
    hexes=[]
    for f in out_dir.glob("*.bin-runtime"):
        b=f.read_text().strip().replace("\n","")
        if not b: continue
        hx=f.with_suffix("").with_suffix(".hex")
        if not b.startswith("0x"): b="0x"+b
        hx.write_text(b)
        hexes.append(hx.name)

    (out_dir/"compile_summary.json").write_text(json.dumps({
        "source":str(src),"solc_version":version,"ok":True,"hex_outputs":hexes
    }, indent=2))
    return {"ok":True,"version":version,"hexes":hexes}

def main():
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sources = sorted([p for p in SRC_DIR.iterdir() if p.suffix in (".sol",".txt")])
    rows=[]
    if not sources:
        print(f"[info] no sources in {SRC_DIR}"); return

    for src in sources:
        num = src.name.split(".")[0]
        out_dir = OUT_DIR/num
        
        # Detect the version from pragma
        detected_version = detect_solc_version(read(src))
        
        # Compile with the detected version
        res = compile_one(src, out_dir, detected_version)
        
        # Store the detected version for the CSV
        pragma_display = detected_version if detected_version else "(none)"
        
        rows.append({
            "file":src.name,
            "pragma_major_minor":pragma_display,
            "solc_version":res["version"],
            "status":"ok" if res["ok"] else "fail",
            "hex_outputs":";".join(res["hexes"]),
            "out_dir":str(out_dir)
        })

    with (OUT_DIR/"compile_batch_summary.csv").open("w", newline="") as fp:
        w=csv.DictWriter(fp, fieldnames=["file","pragma_major_minor","solc_version","status","hex_outputs","out_dir"])
        w.writeheader(); w.writerows(rows)
    print("\n✅ Done. See", OUT_DIR/"compile_batch_summary.csv")

if __name__ == "__main__":
    main()