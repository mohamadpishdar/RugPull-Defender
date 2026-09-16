"""
End-to-end batch pipeline for the rug-pull dataset (dataset.xlsx):

  1. Reads dataset.xlsx and, for each project row, extracts the contract
     address and chain from the hyperlink behind the "Smart Contract
     (online)" column (a scan-site URL such as
     https://bscscan.com/token/0x... or https://etherscan.io/address/0x...).
  2. Fetches the verified Solidity source for that address from the
     matching Etherscan-family explorer, using the unified Etherscan v2
     API (one API key works across every supported chain via the
     chainid parameter).
  3. If the contract is a proxy, also fetches the implementation
     contract's source and merges it in (the real logic, and the likely
     bug/rug-pull mechanism, lives there).
  4. Flattens all retrieved .sol files into a single Solidity source
     (one pragma line, one SPDX line, imports stripped, duplicate file
     bodies dropped).
  5. Writes the flattened result as plain text to
     <output_dir>/<N>.txt, where N is the project's row order in the
     dataset (first data row -> 1.txt, second -> 2.txt, ..., up to
     1000.txt), NOT the (occasionally inconsistent) number embedded in
     the offline-source-code hyperlink.
  6. Writes a run_log.csv summarizing status, chain, address, contract
     name, and proxy info for every row, so failures can be inspected
     and re-run later.

Usage:
    python audit_batch_fetch_flatten.py

All configuration (API key, paths, rate limit) is in the CONFIG block
right below the imports. No command-line arguments are required.
"""

import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import openpyxl

# ============================== CONFIG ===================================

# Get a free key at https://etherscan.io/apis. One key now works across
# every Etherscan-family chain via the v2 unified API (etherscan.io,
# bscscan.com, polygonscan.com, arbiscan.io, basescan.org, etc).
API_KEY = ""

XLSX_PATH = "dataset.xlsx"
SHEET_NAME = None  # None = first/active sheet
ONLINE_COLUMN_HEADER = "Smart Contract (online)"

OUTPUT_DIR = "./flattened_txt"
LOG_PATH = "./run_log.csv"

API_URL = "https://api.etherscan.io/v2/api"
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_CALLS = 0.25  # stay under free-tier 5 req/s (2 calls per proxy contract)
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0

# Map the scan-site domain found in the "online" hyperlink to its
# Etherscan v2 chainid. Extend this if the dataset contains chains not
# listed here.
DOMAIN_TO_CHAINID = {
    "etherscan.io": 1,
    "ww6.etherscan.io": 1,
    "www.etherscan.io": 1,
    "bscscan.com": 56,
    "www.bscscan.com": 56,
    "polygonscan.com": 137,
    "www.polygonscan.com": 137,
    "arbiscan.io": 42161,
    "optimistic.etherscan.io": 10,
    "ftmscan.com": 250,
    "snowscan.xyz": 43114,
    "snowtrace.io": 43114,
    "cronoscan.com": 25,
    "basescan.org": 8453,
    "blastscan.io": 81457,
    "moonscan.io": 1284,
    "moonriver.moonscan.io": 1285,
}

# ============================ END CONFIG ==================================


IMPORT_RE = re.compile(r'^\s*import\b.*?;', re.MULTILINE)
PRAGMA_RE = re.compile(r'^\s*pragma\s+solidity[^;]*;', re.MULTILINE)
SPDX_RE = re.compile(r'^\s*//\s*SPDX-License-Identifier:.*$', re.MULTILINE)
ADDR_RE = re.compile(r'0x[a-fA-F0-9]{40}')


# --------------------------- dataset parsing -------------------------------

def load_dataset_entries(xlsx_path: str, sheet_name):
    """Return a list of dicts: {number, project_title, address, chainid, domain, url}
    in row order. `number` is 1-based over the data rows (not the Excel row
    index and not the number embedded in the offline hyperlink)."""
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb[sheet_name] if sheet_name else wb.active

    header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    try:
        title_col = header.index("Project Title") + 1
    except ValueError:
        title_col = 1
    try:
        online_col = header.index(ONLINE_COLUMN_HEADER) + 1
    except ValueError:
        raise RuntimeError(f'Column "{ONLINE_COLUMN_HEADER}" not found in header: {header}')

    entries = []
    number = 0
    for row in ws.iter_rows(min_row=2):
        if all(c.value is None for c in row):
            continue
        number += 1
        title_cell = row[title_col - 1]
        online_cell = row[online_col - 1]

        entry = {
            "number": number,
            "project_title": title_cell.value,
            "address": None,
            "chainid": None,
            "domain": None,
            "url": None,
            "error": None,
        }

        url = online_cell.hyperlink.target if online_cell.hyperlink else None
        if not url:
            entry["error"] = "no hyperlink in online-source column"
            entries.append(entry)
            continue

        entry["url"] = url
        m = re.search(r'https?://([^/]+)/', url)
        domain = m.group(1) if m else None
        entry["domain"] = domain

        addr_m = ADDR_RE.search(url)
        if not addr_m:
            entry["error"] = f"no address found in url: {url}"
            entries.append(entry)
            continue
        entry["address"] = addr_m.group(0)

        chainid = DOMAIN_TO_CHAINID.get(domain)
        if chainid is None:
            entry["error"] = f"unknown domain, add it to DOMAIN_TO_CHAINID: {domain}"
            entries.append(entry)
            continue
        entry["chainid"] = chainid

        entries.append(entry)

    return entries


# --------------------------- etherscan v2 fetch -----------------------------

def api_call(params: dict):
    url = API_URL + "?" + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(RETRY_BACKOFF * attempt)
    raise RuntimeError(f"API call failed after {MAX_RETRIES} retries: {last_err}")


def fetch_source(address: str, chainid: int, api_key: str) -> dict:
    data = api_call({
        "chainid": chainid,
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
        "apikey": api_key,
    })
    if data.get("status") != "1":
        raise RuntimeError(f"API error: {data.get('message')} - {data.get('result')}")
    result = data["result"][0]
    if not result.get("SourceCode"):
        raise RuntimeError(f"no verified source code on chain {chainid}")
    return result


def extract_files(result: dict) -> dict:
    """Return {filename: content} for every source file in a getsourcecode result."""
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


# ------------------------------- flattening ---------------------------------

def strip_imports(content: str) -> str:
    return IMPORT_RE.sub('', content)


def find_first(pattern: re.Pattern, content: str):
    m = pattern.search(content)
    return m.group(0).strip() if m else None


def flatten(files: dict, header_comment: str = "") -> str:
    pragma = None
    spdx = None
    seen_bodies = set()
    bodies = []

    for _, content in files.items():
        if pragma is None:
            pragma = find_first(PRAGMA_RE, content)
        if spdx is None:
            spdx = find_first(SPDX_RE, content)

        body = strip_imports(content)
        body = PRAGMA_RE.sub('', body)
        body = SPDX_RE.sub('', body)
        body = body.strip()

        if not body or body in seen_bodies:
            continue
        seen_bodies.add(body)
        bodies.append(body)

    header_lines = []
    if header_comment:
        header_lines.append(header_comment)
    header_lines.append(spdx or '// SPDX-License-Identifier: UNLICENSED')
    header_lines.append(pragma or 'pragma solidity ^0.8.0;')

    return '\n'.join(header_lines) + '\n\n' + '\n\n'.join(bodies) + '\n'


# --------------------------------- driver -----------------------------------

def process_entry(entry: dict, api_key: str, output_dir: str) -> dict:
    number = entry["number"]
    address = entry["address"]
    chainid = entry["chainid"]

    log = {
        "number": number,
        "project_title": entry["project_title"],
        "address": address,
        "chainid": chainid,
        "status": "FAILED",
        "contract_name": None,
        "is_proxy": None,
        "implementation_address": None,
        "detail": entry["error"] or "",
    }

    if entry["error"]:
        return log

    try:
        result = fetch_source(address, chainid, api_key)
        files = extract_files(result)
        header = f"// number: {number}\n// project: {entry['project_title']}\n// address: {address}\n// chainid: {chainid}"

        log["contract_name"] = result.get("ContractName")
        is_proxy = result.get("Proxy") == "1"
        impl_addr = result.get("Implementation") or None
        log["is_proxy"] = is_proxy
        log["implementation_address"] = impl_addr

        if is_proxy and impl_addr:
            time.sleep(SLEEP_BETWEEN_CALLS)
            try:
                impl_result = fetch_source(impl_addr, chainid, api_key)
                impl_files = extract_files(impl_result)
                # prefix implementation filenames so they never collide
                # with same-named proxy files, then merge.
                for fn, content in impl_files.items():
                    files[f"impl_{fn}"] = content
                header += f"\n// proxy: true, implementation: {impl_addr} ({impl_result.get('ContractName')})"
            except Exception as e:
                header += f"\n// proxy: true, implementation: {impl_addr} (FAILED TO FETCH: {e})"

        flat = flatten(files, header_comment=header)
        out_path = os.path.join(output_dir, f"{number}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(flat)

        log["status"] = "OK"
        log["detail"] = f"{len(files)} file(s)"
    except Exception as e:
        log["detail"] = str(e)

    return log


def main():
    if not API_KEY or API_KEY == "PUT_YOUR_API_KEY_HERE":
        print("ERROR: set API_KEY near the top of this script first.")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    entries = load_dataset_entries(XLSX_PATH, SHEET_NAME)
    print(f"Loaded {len(entries)} row(s) from {XLSX_PATH}\n")

    logs = []
    ok = failed = 0
    for entry in entries:
        print(f"[{entry['number']}/{len(entries)}] {entry['project_title']} "
              f"({entry['address']}, chain {entry['chainid']}) ...")
        log = process_entry(entry, API_KEY, OUTPUT_DIR)
        logs.append(log)
        if log["status"] == "OK":
            ok += 1
            print(f"  OK -> {OUTPUT_DIR}/{entry['number']}.txt "
                  f"({log['contract_name']}, {log['detail']})")
        else:
            failed += 1
            print(f"  FAILED: {log['detail']}")
        time.sleep(SLEEP_BETWEEN_CALLS)

    with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(logs[0].keys()))
        writer.writeheader()
        writer.writerows(logs)

    print(f"\nDone: {ok} succeeded, {failed} failed.")
    print(f"Flattened contracts: {OUTPUT_DIR}/<number>.txt")
    print(f"Full log: {LOG_PATH}")


if __name__ == "__main__":
    main()
