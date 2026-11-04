#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rename user-defined Solidity identifiers in flattened sources without
breaking compiler syntax.

Reads:  data/flatten_source_code/*.txt      (override with --src)
Writes: data/obfuscated_contracts/*.txt     (override with --out)

Every renamed identifier becomes `_x` followed by six hexadecimal digits,
derived from a SHA-256 hash of the file name and the original identifier,
so the mapping is deterministic and consistent within each file.

Protected (never renamed):
  - language keywords / types / units
  - globals (abi, msg, block, tx, this, super, now, keccak256, ...)
  - modifier placeholder `_`
  - address/array/abi/block/msg members (transfer, length, selector, ...)
  - Yul opcodes inside `assembly { ... }`
  - identifiers in `pragma` / `import` statements (and imported symbols)
  - comments, strings, hex/unicode literals, numeric literals (incl. 1_000, 1e18)
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "data" / "flatten_source_code"
OUT_DIR = ROOT / "data" / "obfuscated_contracts"

KEYWORDS = {
    "abstract", "after", "alias", "anonymous", "apply", "as", "assembly",
    "auto", "break", "calldata", "case", "catch", "constant", "constructor",
    "continue", "contract", "copyof", "default", "define", "delete", "do",
    "else", "emit", "enum", "error", "event", "external", "fallback", "false",
    "final", "for", "function", "global", "hex", "if", "immutable", "import",
    "in", "indexed", "inline", "interface", "internal", "is", "let", "library",
    "macro", "mapping", "match", "memory", "modifier", "mutable", "new", "null",
    "of", "override", "partial", "payable", "pragma", "private", "promise",
    "public", "pure", "receive", "reference", "relocatable", "return", "returns",
    "revert", "sealed", "sizeof", "static", "storage", "struct", "supports",
    "switch", "throw", "true", "try", "type", "typedef", "typeof", "unchecked",
    "unicode", "using", "var", "view", "virtual", "while",
    "Error", "Panic",
}

TYPES = {
    "address", "bool", "string", "bytes", "byte", "int", "uint",
    "fixed", "ufixed",
}
for _i in range(8, 257, 8):
    TYPES.add(f"uint{_i}")
    TYPES.add(f"int{_i}")
for _i in range(1, 33):
    TYPES.add(f"bytes{_i}")

UNITS = {
    "wei", "gwei", "ether", "seconds", "minutes", "hours", "days", "weeks",
    "years", "szabo", "finney",
}

BUILTINS = {
    "abi", "block", "msg", "tx", "now", "super", "this",
    "keccak256", "sha256", "sha3", "ripemd160", "ecrecover",
    "addmod", "mulmod", "selfdestruct", "suicide", "gasleft",
    "blockhash", "blobhash", "require", "assert", "revert",
}

# Keep these globally so `addr.transfer` / `arr.length` / `fn.selector` stay valid
# even when the same spelling is also a user function name (e.g. ERC20.transfer).
PROTECTED_NAMES = {
    "encode", "encodePacked", "encodeWithSelector", "encodeWithSignature",
    "encodeCall", "decode",
    "chainid", "coinbase", "difficulty", "gaslimit", "number", "timestamp",
    "basefee", "blobbasefee", "prevrandao",
    "data", "sender", "sig", "value", "gas", "gasprice", "origin",
    "selector", "creationCode", "runtimeCode", "interfaceId", "min", "max",
    "name", "balance", "code", "codehash",
    "transfer", "send", "call", "delegatecall", "staticcall", "callcode",
    "push", "pop", "length", "slot", "offset",
    # user-defined value types: Type.wrap / Type.unwrap
    "wrap", "unwrap",
    # string.concat / bytes.concat
    "concat",
}

YUL_BUILTINS = {
    "stop", "add", "sub", "mul", "div", "sdiv", "mod", "smod", "exp", "not",
    "lt", "gt", "slt", "sgt", "eq", "iszero", "and", "or", "xor", "byte",
    "shl", "shr", "sar", "addmod", "mulmod", "signextend", "keccak256", "pop",
    "mload", "mstore", "mstore8", "sload", "sstore", "tload", "tstore", "mcopy",
    "gas", "address", "balance", "selfbalance", "caller", "callvalue",
    "calldataload", "calldatasize", "calldatacopy", "codesize", "codecopy",
    "extcodesize", "extcodecopy", "returndatasize", "returndatacopy",
    "extcodehash", "create", "create2", "call", "callcode", "delegatecall",
    "staticcall", "return", "revert", "selfdestruct", "invalid",
    "log0", "log1", "log2", "log3", "log4",
    "chainid", "origin", "gasprice", "blockhash", "blobhash", "coinbase",
    "timestamp", "number", "difficulty", "prevrandao", "gaslimit", "basefee",
    "blobbasefee", "pc", "msize", "gas",
    "let", "if", "switch", "case", "default", "for", "break", "continue",
    "function", "leave", "true", "false", "hex", "dataoffset", "datasize",
    "datacopy", "setimmutable", "loadimmutable", "linker", "linkersymbol",
    "memoryguard", "verbatim",
}

ALWAYS_PROTECTED = KEYWORDS | TYPES | UNITS | BUILTINS | PROTECTED_NAMES | {"_"}

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
IMPORT_RE = re.compile(r"\bimport\b[\s\S]*?;")
NATSPEC_PARAM_RE = re.compile(
    r"(@param(?:\s+\[[^\]]+\])?(?:\s+\{[^}]+\})?\s+)([A-Za-z_][A-Za-z0-9_]*)"
)
NATSPEC_RETURN_RE = re.compile(
    r"(@return(?:\s+\{[^}]+\})?\s+)([A-Za-z_][A-Za-z0-9_]*)"
)
NATSPEC_INHERITDOC_RE = re.compile(
    r"(@inheritdoc\s+)([A-Za-z_][A-Za-z0-9_]*)"
)
ASSEMBLY_SLOT_SUFFIXES = ("_slot", "_offset")


def _skip_ws_and_comments(src: str, i: int) -> int:
    n = len(src)
    while i < n:
        if src[i] in " \t\r\n":
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            return n if j < 0 else j
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            return n if j < 0 else j + 2
        break
    return i


def _scan_string(src: str, i: int) -> int:
    quote = src[i]
    i += 1
    n = len(src)
    while i < n:
        ch = src[i]
        if ch == "\\":
            i += 2
            continue
        if ch == quote:
            return i + 1
        i += 1
    return n


def _scan_number(src: str, i: int) -> int:
    n = len(src)
    if src.startswith("0x", i) or src.startswith("0X", i):
        j = i + 2
        while j < n:
            ch = src[j]
            if ch in "0123456789abcdefABCDEF":
                j += 1
            elif ch == "_" and j + 1 < n and src[j + 1] in "0123456789abcdefABCDEF":
                j += 1
            else:
                break
        return j

    j = i
    while j < n:
        if src[j].isdigit():
            j += 1
        elif src[j] == "_" and j + 1 < n and src[j + 1].isdigit():
            j += 1
        else:
            break
    if j < n and src[j] in "eE":
        k = j + 1
        if k < n and src[k] in "+-":
            k += 1
        if k < n and src[k].isdigit():
            j = k
            while j < n:
                if src[j].isdigit():
                    j += 1
                elif src[j] == "_" and j + 1 < n and src[j + 1].isdigit():
                    j += 1
                else:
                    break
    return j


def _strip_comments_for_scan(src: str) -> str:
    out = []
    i, n = 0, len(src)
    while i < n:
        if src.startswith("//", i):
            j = src.find("\n", i)
            if j < 0:
                break
            out.append("\n")
            i = j + 1
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            chunk = src[i:n if j < 0 else j + 2]
            out.append("\n" * chunk.count("\n"))
            i = n if j < 0 else j + 2
            continue
        if src[i] in "'\"":
            j = _scan_string(src, i)
            out.append(" " * (j - i))
            i = j
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def imported_symbols(src: str) -> set[str]:
    symbols: set[str] = set()
    scanned = _strip_comments_for_scan(src)
    for stmt in IMPORT_RE.findall(scanned):
        for brace in re.finditer(r"\{([^}]+)\}", stmt):
            for part in brace.group(1).split(","):
                part = part.strip()
                if not part:
                    continue
                toks = part.split()
                symbols.add(toks[-1] if toks else part)
        as_m = re.search(r"\bas\s+([A-Za-z_][A-Za-z0-9_]*)", stmt)
        if as_m:
            symbols.add(as_m.group(1))
        for path in re.findall(r"""['"]([^'"]+)['"]""", stmt):
            stem = Path(path).stem
            if IDENT_RE.fullmatch(stem):
                symbols.add(stem)
    return symbols


def _rewrite_natspec(comment: str, mapping: dict[str, str]) -> str:
    """Keep @param / @return names in lockstep with renamed function arguments."""

    def repl(m: re.Match[str]) -> str:
        return m.group(1) + mapping.get(m.group(2), m.group(2))

    comment = NATSPEC_PARAM_RE.sub(repl, comment)
    comment = NATSPEC_RETURN_RE.sub(repl, comment)
    comment = NATSPEC_INHERITDOC_RE.sub(repl, comment)
    return comment


def _rewrite_natspec_in_source(src: str, mapping: dict[str, str]) -> str:
    if not mapping:
        return src
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(_rewrite_natspec(src[i:j], mapping))
            i = j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(_rewrite_natspec(src[i:j], mapping))
            i = j
            continue
        if src[i] in "'\"":
            j = _scan_string(src, i)
            out.append(src[i:j])
            i = j
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def _obfuscated_name(file_key: str, ident: str, used: set[str]) -> str:
    digest = hashlib.sha256(f"{file_key}:{ident}".encode("utf-8")).hexdigest()
    i = 0
    while True:
        cand = f"_x{digest[i:i + 6]}"
        if cand not in used and cand != ident:
            used.add(cand)
            return cand
        i += 1
        if i + 6 > len(digest):
            digest = hashlib.sha256((digest + ident).encode("utf-8")).hexdigest()
            i = 0


def obfuscate_source(src: str, file_key: str) -> str:
    protected = set(ALWAYS_PROTECTED)
    protected |= imported_symbols(src)

    mapping: dict[str, str] = {}
    used_names: set[str] = set()
    out: list[str] = []

    i = 0
    n = len(src)
    assembly_depth = 0
    expect_assembly_brace = False
    brace_depth = 0

    def copy_until_semicolon() -> None:
        nonlocal i
        while i < n:
            if src.startswith("//", i):
                j = src.find("\n", i)
                j = n if j < 0 else j
                out.append(src[i:j])
                i = j
                continue
            if src.startswith("/*", i):
                j = src.find("*/", i + 2)
                j = n if j < 0 else j + 2
                out.append(src[i:j])
                i = j
                continue
            if src[i] in "'\"":
                j = _scan_string(src, i)
                out.append(src[i:j])
                i = j
                continue
            out.append(src[i])
            if src[i] == ";":
                i += 1
                return
            i += 1

    while i < n:
        ch = src[i]

        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(src[i:j])
            i = j
            continue

        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(src[i:j])
            i = j
            continue

        if ch in "'\"":
            j = _scan_string(src, i)
            out.append(src[i:j])
            i = j
            continue

        if ch.isdigit():
            j = _scan_number(src, i)
            out.append(src[i:j])
            i = j
            continue

        m = IDENT_RE.match(src, i)
        if m:
            ident = m.group(0)
            nxt = m.end()

            if ident == "pragma" or ident == "import":
                out.append(ident)
                i = nxt
                copy_until_semicolon()
                continue

            if ident == "assembly" and assembly_depth == 0:
                expect_assembly_brace = True

            in_yul = assembly_depth > 0
            suffix = ""
            base = ident
            if in_yul:
                for suf in ASSEMBLY_SLOT_SUFFIXES:
                    if ident.endswith(suf) and ident != suf:
                        base, suffix = ident[: -len(suf)], suf
                        break

            freeze = (
                ident in protected
                or base in protected
                or (in_yul and ident in YUL_BUILTINS)
                or (in_yul and base in YUL_BUILTINS)
            )
            if freeze:
                out.append(ident)
            else:
                if base not in mapping:
                    mapping[base] = _obfuscated_name(file_key, base, used_names)
                out.append(mapping[base] + suffix)
            i = nxt
            continue

        if ch == "{":
            brace_depth += 1
            if expect_assembly_brace and assembly_depth == 0:
                assembly_depth = brace_depth
                expect_assembly_brace = False
            out.append(ch)
            i += 1
            continue

        if ch == "}":
            if assembly_depth and brace_depth == assembly_depth:
                assembly_depth = 0
            brace_depth = max(0, brace_depth - 1)
            out.append(ch)
            i += 1
            continue

        if not ch.isspace() and ch not in ("(", ")", '"', "'"):
            # `assembly ("memory-safe") {` — keep waiting for `{`
            if not expect_assembly_brace:
                pass
        out.append(ch)
        i += 1

    return _rewrite_natspec_in_source("".join(out), mapping)


def sanity_check(original: str, obfuscated: str) -> list[str]:
    issues = []
    if "pragma solidity" in original and "pragma solidity" not in obfuscated:
        issues.append("pragma solidity missing")
    if re.search(r"\bmodifier\b", original) and not re.search(
        r"modifier\s+\w+\s*\([^)]*\)\s*\{[^}]*\b_\s*;", obfuscated, re.S
    ):
        # Some modifiers use `_` without semicolon spacing variants; check raw `_`
        if re.search(r"\bmodifier\b", obfuscated) and not re.search(r"(?<![\w])_(?![\w])", obfuscated):
            issues.append("modifier placeholder `_` missing")
    if "msg.sender" in original and "msg.sender" not in obfuscated:
        issues.append("msg.sender was renamed")
    if "abi.encode" in original and "abi.encode" not in obfuscated:
        issues.append("abi.encode was renamed")
    if re.search(r"\bextcodehash\b", original) and not re.search(r"\bextcodehash\b", obfuscated):
        issues.append("extcodehash opcode was renamed")
    if re.search(r"\b1_000\b", original) and not re.search(r"\b1_000\b", obfuscated):
        issues.append("numeric separator literal was broken")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=SRC_DIR)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--limit", type=int, default=0, help="only first N files")
    parser.add_argument("--ids", default="", help="comma-separated stems to rewrite (e.g. 7,22,289)")
    parser.add_argument(
        "--failed-vs-flatten",
        action="store_true",
        help="only rewrite IDs that compiled in flatten but failed after obfuscation",
    )
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    files = sorted(args.src.glob("*.txt"), key=lambda p: int(p.stem) if p.stem.isdigit() else p.stem)
    if args.failed_vs_flatten:
        import csv
        flat_csv = ROOT / "data" / "bytecode_compile_flatten_solcselect" / "compile_batch_summary.csv"
        obf_csv = ROOT / "data" / "bytecode_compile_obfuscated_solcselect" / "compile_batch_summary.csv"
        flat = {int(Path(r["file"]).stem): r["status"] for r in csv.DictReader(flat_csv.open())}
        obf = {int(Path(r["file"]).stem): r["status"] for r in csv.DictReader(obf_csv.open())}
        wanted = {i for i in flat if flat.get(i) == "ok" and obf.get(i) == "fail"}
        files = [p for p in files if p.stem.isdigit() and int(p.stem) in wanted]
        print(f"[info] rewriting {len(files)} flatten-ok / obfuscated-fail files")
    elif args.ids:
        wanted = {s.strip() for s in args.ids.split(",") if s.strip()}
        files = [p for p in files if p.stem in wanted]
    if args.limit:
        files = files[: args.limit]
    if not files:
        raise SystemExit(f"no sources in {args.src}")

    n_ok = 0
    n_warn = 0
    for src_path in files:
        # Binary I/O: flatten files often use mixed `\r\n` / `\r\r\n`.
        # Text mode would turn extra `\r` into extra blank lines.
        text = src_path.read_bytes().decode("utf-8", errors="ignore")
        obf = obfuscate_source(text, src_path.stem)
        dest = args.out / src_path.name
        dest.write_bytes(obf.encode("utf-8"))
        issues = sanity_check(text, obf)
        n_ok += 1
        if issues:
            n_warn += 1
            print(f"[warn] {src_path.name}: {', '.join(issues)}")
        if n_ok % 100 == 0:
            print(f"[info] wrote {n_ok}/{len(files)}")

    print(f"Done. {n_ok} files → {args.out} ({n_warn} sanity warnings)")


if __name__ == "__main__":
    main()
