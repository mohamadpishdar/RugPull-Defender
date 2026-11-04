#!/usr/bin/env python3
"""
Turn Gigahorse/CRPWarner output into one CSV per condition.

A project is flagged for a pattern when the corresponding CRPWarner relation
is non-empty in its results:
    HiddenMintFunction -> HiddenMint
    LeakingToken       -> LeakingToken
    LimitingSellOrder  -> LimitingSell
Analyses that hit the time limit are marked in the Timeout column and keep
whatever relations were produced. Projects without bytecode get empty flags.

Usage:
    python collect_results.py --results results_clean.json [more.json ...] \
        --log bytecode/log_clean.csv --out crpwarner_results_clean.csv
"""

import argparse
import json
import re

import pandas as pd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", nargs="+", required=True, help="Gigahorse results.json file(s)")
    ap.add_argument("--log", required=True, help="log_<condition>.csv from prepare_bytecode.py")
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=1000, help="number of projects in the dataset")
    args = ap.parse_args()

    main_contract = pd.read_csv(args.log).set_index("GroupID")["main"]
    flags, timeouts = {}, set()
    for path in args.results:
        for name, relations, *_ in json.load(open(path)):
            gid = int(name.replace(".hex", ""))
            rel = set(relations)
            flags[gid] = dict(HiddenMint=int("HiddenMintFunction" in rel),
                              LeakingToken=int("LeakingToken" in rel),
                              LimitingSell=int("LimitingSellOrder" in rel))
        try:
            for line in open(re.sub(r"\.json$", ".log", path)):
                m = re.match(r"\s*\d+: (\d+)\.hex completed.*Timeouts in", line)
                if m:
                    timeouts.add(int(m.group(1)))
        except FileNotFoundError:
            pass

    rows = []
    for gid in range(1, args.n + 1):
        name = main_contract.get(gid)
        row = dict(GroupID=gid, Artifact=name if isinstance(name, str) else "no hex file")
        if gid in flags:
            row.update(flags[gid], RugPull=bool(sum(flags[gid].values())), Timeout=gid in timeouts)
        else:
            row.update(HiddenMint=None, LeakingToken=None, LimitingSell=None, RugPull=False, Timeout=None)
        rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(args.out, index=False)
    print(f"analysed {len(flags)} | flagged {int(out.RugPull.sum())} | timeouts {len(timeouts)} -> {args.out}")


if __name__ == "__main__":
    main()
