"""
Batch-fetch verified Solidity source code for a list of smart contracts
from Etherscan (and any Etherscan-family explorer via the unified v2 API
and chainid parameter), saving each contract's full source as a single
.zip file named after its address.

Input: a CSV/text file with one contract per line:
    address,chainid
Blank lines and lines starting with # are ignored. chainid can be omitted
(defaults to 1 = Ethereum).

Usage:
    python 01_fetch_contracts.py addresses.txt [output_dir]

Example addresses.txt:
    0xE85A08Cf316F695eBE7c13736C8Cc38a7Cc3e944,1
    0x3de669c4F1f167a8aFBc9993E4753b84b576426f,56
    0x17e8Ca1b4798B97602895f63206afCd1Fc90Ca5f

Output: <output_dir>/<address>.zip for each successfully fetched contract,
containing every source file Etherscan returns for it (one .sol per file
for multi-file / Standard-JSON-Input contracts, or a single .sol for
simple ones), plus a metadata.json with contract name, compiler version,
and proxy/implementation info if relevant.

Set your API key in the ETHERSCAN_API_KEY environment variable before
running the script. (Get a free key at https://etherscan.io/apis -- one key
works across all Etherscan-family chains via the v2 API.)

Common chain IDs: 1 = Ethereum, 56 = BNB Chain, 137 = Polygon,
42161 = Arbitrum, 10 = Optimism, 43114 = Avalanche, 250 = Fantom.
"""

import os
import sys
import json
import time
import zipfile
import urllib.request
import urllib.parse

# The Etherscan API key is read from the ETHERSCAN_API_KEY environment variable.
# One key now works across all Etherscan-family chains via the v2 API.
API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")

API_URL = "https://api.etherscan.io/v2/api"


def fetch_source(address: str, chainid: str, api_key: str) -> dict:
    params = {
        "chainid": chainid,
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
        "apikey": api_key,
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read().decode())

    if data.get("status") != "1":
        raise RuntimeError(f"API error: {data.get('message')} - {data.get('result')}")

    result = data["result"][0]
    if not result.get("SourceCode"):
        raise RuntimeError(f"No verified source code found on chain {chainid}")
    return result


def extract_files(result: dict):
    """Return a dict of {filename: content} for every source file."""
    raw = result["SourceCode"]
    text = raw.strip()
    parsed = None
    if text.startswith("{") and text.endswith("}"):
        candidate = text
        if candidate.startswith("{{") and candidate.endswith("}}"):
            candidate = candidate[1:-1]
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None

    if parsed is not None:
        sources = parsed.get("sources", parsed)
        files = {}
        for filename, filedata in sources.items():
            content = filedata.get("content", "") if isinstance(filedata, dict) else str(filedata)
            safe_name = filename.lstrip("./").replace("@", "at_")
            files[safe_name] = content
        return files
    else:
        name = result.get("ContractName") or "contract"
        return {f"{name}.sol": raw}


def process_one(address: str, chainid: str, api_key: str, output_dir: str) -> bool:
    print(f"Fetching {address} on chain {chainid} ...")
    try:
        result = fetch_source(address, chainid, api_key)
        files = extract_files(result)

        meta = {
            "address": address,
            "chainid": chainid,
            "contract_name": result.get("ContractName"),
            "compiler_version": result.get("CompilerVersion"),
            "optimization_used": result.get("OptimizationUsed"),
            "runs": result.get("Runs"),
            "is_proxy": result.get("Proxy") == "1",
            "implementation_address": result.get("Implementation") or None,
            "file_count": len(files),
        }

        zip_path = os.path.join(output_dir, f"{address}.zip")
        os.makedirs(output_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, content in files.items():
                zf.writestr(filename, content)
            zf.writestr("metadata.json", json.dumps(meta, indent=2))

        print(f"  OK -> {zip_path}  ({meta['contract_name']}, {len(files)} file(s), {meta['compiler_version']})")
        if meta["is_proxy"]:
            print(f"  NOTE: this is a proxy. Implementation contract: {meta['implementation_address']}")
            print(f"        The real logic (and likely the bug) lives there -- fetch it separately too.")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def read_list(path: str):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            address = parts[0]
            chainid = parts[1] if len(parts) > 1 and parts[1] else "1"
            entries.append((address, chainid))
    return entries


def main():
    api_key = API_KEY
    if not api_key:
        print("ERROR: set the ETHERSCAN_API_KEY environment variable first.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    list_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "./sources_zip"

    entries = read_list(list_path)
    print(f"Loaded {len(entries)} contract(s) from {list_path}\n")

    ok, failed = 0, 0
    for address, chainid in entries:
        success = process_one(address, chainid, api_key, output_dir)
        ok += success
        failed += not success
        time.sleep(0.25)  # stay under free-tier rate limit (5 req/s)

    print(f"\nDone: {ok} succeeded, {failed} failed. Zips are in: {output_dir}")


if __name__ == "__main__":
    main()
