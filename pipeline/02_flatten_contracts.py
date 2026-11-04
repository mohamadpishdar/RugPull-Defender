"""
Flatten every contract's source code into a single .sol file.

Works on a root directory that contains, for each contract, EITHER:
  - a subfolder with one or more .sol files (possibly in subfolders,
    mirroring import paths), OR
  - a .zip file (e.g. produced by 01_fetch_contracts.py) containing
    one or more .sol files.

For each contract found, it:
  1. Collects every .sol file's content.
  2. Keeps only ONE pragma solidity line (the first one found) and ONE
     SPDX-License-Identifier line, and drops all the rest.
  3. Removes every `import ...;` line (single or multi-line imports),
     since after concatenation everything lives in one file and Solidity
     does not require forward declarations.
  4. Drops exact duplicate file contents (the same file imported from two
     different paths, common with OpenZeppelin).
  5. Writes the result to <output_dir>/<contract_name>_flat.sol.

Usage:
    python 02_flatten_contracts.py <root_dir> [output_dir]

Example:
    python 02_flatten_contracts.py ./sources_zip ./flattened
    python 02_flatten_contracts.py ./sources_extracted ./flattened

Note: this is a straightforward textual flattener (concatenate + strip
imports/duplicate pragmas), not a full import-graph resolver. It works
well for the vast majority of verified contracts pulled from Etherscan,
but for contracts with deep/unusual import structures you may still need
to eyeball the result and fix an occasional missing piece by hand.
"""

import os
import re
import sys
import zipfile

IMPORT_RE = re.compile(r'^\s*import\b.*?;', re.MULTILINE)
PRAGMA_RE = re.compile(r'^\s*pragma\s+solidity[^;]*;', re.MULTILINE)
SPDX_RE = re.compile(r'^\s*//\s*SPDX-License-Identifier:.*$', re.MULTILINE)


def strip_imports(content: str) -> str:
    return IMPORT_RE.sub('', content)


def find_first(pattern: re.Pattern, content: str):
    m = pattern.search(content)
    return m.group(0).strip() if m else None


def collect_sol_files_from_dir(path: str):
    files = {}
    for dirpath, _, filenames in os.walk(path):
        for fn in filenames:
            if fn.endswith('.sol'):
                full = os.path.join(dirpath, fn)
                with open(full, 'r', encoding='utf-8', errors='ignore') as f:
                    files[full] = f.read()
    return files


def collect_sol_files_from_zip(path: str):
    files = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.endswith('.sol'):
                files[name] = zf.read(name).decode(errors='ignore')
    return files


def flatten(files: dict) -> str:
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

        if not body:
            continue
        # Skip exact duplicates (same file pulled in via multiple import paths)
        if body in seen_bodies:
            continue
        seen_bodies.add(body)
        bodies.append(body)

    header_lines = []
    if spdx:
        header_lines.append(spdx)
    else:
        header_lines.append('// SPDX-License-Identifier: UNLICENSED')
    if pragma:
        header_lines.append(pragma)
    else:
        header_lines.append('pragma solidity ^0.8.0;')

    return '\n'.join(header_lines) + '\n\n' + '\n\n'.join(bodies) + '\n'


def process_root(root_dir: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    entries = sorted(os.listdir(root_dir))
    ok, skipped = 0, 0

    for entry in entries:
        full = os.path.join(root_dir, entry)

        if entry.lower().endswith('.zip') and os.path.isfile(full):
            name = entry[:-4]
            print(f"Flattening (zip) {entry} ...")
            try:
                files = collect_sol_files_from_zip(full)
            except Exception as e:
                print(f"  FAILED to read zip: {e}")
                skipped += 1
                continue
        elif os.path.isdir(full):
            name = entry
            print(f"Flattening (folder) {entry} ...")
            files = collect_sol_files_from_dir(full)
        else:
            continue

        if not files:
            print(f"  SKIPPED: no .sol files found")
            skipped += 1
            continue

        flat = flatten(files)
        out_path = os.path.join(output_dir, f"{name}_flat.sol")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(flat)
        print(f"  OK -> {out_path}  ({len(files)} source file(s) merged)")
        ok += 1

    print(f"\nDone: {ok} flattened, {skipped} skipped. Output in: {output_dir}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    root_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "./flattened"
    process_root(root_dir, output_dir)


if __name__ == "__main__":
    main()
