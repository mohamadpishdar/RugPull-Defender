#!/usr/bin/env python3
"""
Remove the metadata comment block from the top of every flattened source file.

When the dataset was assembled, each flattened file received a short comment
header that records the project's index in the dataset, its name, its contract
address, and its chain identifier, for example:

    // number: 851
    // project: pTokens TLOS (TLOS)
    // address: 0x7825e833d495f3d1c28872415a4aee339d26ac88
    // chainid: 1

The project indices follow the class order of the dataset, so the header
leaks the label. This script removes every comment line of this form,
wherever it occurs in the file, and leaves all other lines unchanged. It is applied to both the original and the
renamed (obfuscated) sources before any experiment.

Usage:
    python 03_strip_metadata_header.py <input.zip> <output.zip>

Example:
    python 03_strip_metadata_header.py flatten_source_code.zip flatten_source_code_noheader.zip
"""

import re
import sys
import zipfile

HEADER_LINE = re.compile(r"^[ \t]*//[ \t]*(number|project|address|chainid)[ \t]*:[^\r\n]*(\r\n|\n|\r)?",
                         re.IGNORECASE | re.MULTILINE)


def strip_header(text: str) -> str:
    """Remove every metadata comment line from a source file."""
    return HEADER_LINE.sub("", text)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    src, dst = sys.argv[1], sys.argv[2]
    changed = 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.endswith(".txt"):
                text = data.decode("utf-8", errors="ignore")
                new = strip_header(text)
                changed += new != text
                data = new.encode("utf-8")
            zout.writestr(info.filename, data)
    print(f"Removed the metadata header from {changed} files -> {dst}")


if __name__ == "__main__":
    main()
