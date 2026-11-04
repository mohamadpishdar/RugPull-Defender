"""
W2: Forta-style lexical rule set tailored to rug pulls.

Each rule group is a regular expression with a fixed severity weight taken
from the rug-pull taxonomy of Sun et al. (SoK, 2025). A group contributes its
weight once if any of its patterns appears in a code line; the text of
single-line comments is ignored. The score is the sum of the contributed
weights divided by the maximum possible sum, so it lies in [0, 1].

This is a rule set written in the style of the Forta monitoring rules. It is
not one of the official Forta detection bots.

Inside the cascade, the rule groups are pruned on the training folds of each
cross-validation fold (see cascade/evaluate.py): a group is kept only if it
fires in at least ten training contracts and its rug-pull share among those
contracts exceeds the training base rate by five percentage points. The
weights are never changed.
"""

import re

# (pattern, weight). The index of each entry is used as the rule-group id.
RULES = [
    (r'\bmint\s*\(|_mint|mintFrom', 2.5),                                   # 0  minting
    (r'\b_burn|burnFrom|destroyTokens', 2.0),                               # 1  burning
    (r'\bblacklist|isBlacklisted', 3.0),                                    # 2  blacklisting
    (r'\bfreezeAccount|isFrozen', 2.5),                                     # 3  account freezing
    (r'\bonlyOwner|owner\b|Ownable', 2.0),                                  # 4  owner-only access
    (r'\bsetFee|setTax|taxFee|_tax', 2.5),                                  # 5  fee and tax setters
    (r'\b(withdraw|drain|emergencyWithdraw|drainAll|sweep)', 3.0),          # 6  withdrawal and draining
    (r'\btransferOwnership|_owner\s*=', 2.0),                               # 7  ownership transfer
    (r'\bupgradeTo|_implementation', 2.5),                                  # 8  proxy upgrades
    (r'\.call\(|delegatecall', 2.5),                                        # 9  low-level calls
    (r'\bassembly\s*\{', 1.5),                                              # 10 inline assembly
]
MAXS = sum(w for _, w in RULES)


def in_code_context(code: str, pat: str) -> bool:
    """True if `pat` matches a non-empty code line, ignoring single-line comments."""
    for line in code.split('\n'):
        if '//' in line:
            line = line.split('//')[0]
        if line.strip() and re.search(pat, line, re.I):
            return True
    return False


def forta_score(code: str) -> float:
    """Sum of the weights of all rule groups that fire on `code`."""
    return sum(w for p, w in RULES if in_code_context(code, p))


def forta_prob(code: str) -> float:
    """Normalized W2 score over all eleven rule groups, in [0, 1]."""
    return forta_score(code) / MAXS


def rule_hits(code: str) -> list:
    """Binary vector: which of the eleven rule groups fire on `code`."""
    return [in_code_context(code, p) for p, _ in RULES]
