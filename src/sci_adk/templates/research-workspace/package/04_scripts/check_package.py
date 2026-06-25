#!/usr/bin/env python3
"""Package integrity self-check (field-agnostic).

Confirms the manuscript package is internally consistent and submission-clean:
  1. \\ref <-> \\label integrity, figure presence, brace balance (main.tex, si.tex)
  2. every \\cite key resolves to an entry in references.bib (and flags uncited entries)
  3. no toolchain vocabulary leaks into the author-facing prose (names the science, not the
     tool)

Exit 0 iff all three pass. Run from the package root: ``python3 04_scripts/check_package.py``.

This is the reviewer-facing companion to the ``package_requirements_clean`` verify gate: the
gate is the authoritative, in-process deterministic check; this script lets a reviewer who has
only the shipped package (and a Python interpreter) re-run the same structural checks by hand.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
MAN = os.path.join(PKG, "01_manuscript")

# Toolchain terms that must NOT appear in author-facing prose (the science is named instead).
# Mirrors sci-adk's own paper tool-vocabulary gate spirit (render.paper.check_paper_tool_vocabulary).
TOOLVOCAB = [r"sci-adk", r"\bSpec\b", r"\bEvidence\b", r"\bClaim\b", r"belief state",
             r"decision rule", r"four-pane", r"headless audit", r"\bverify\b",
             r"Evidence digest"]


def check_tex(path, check_figs=True):
    """ref/label integrity + figure presence + brace balance for one .tex. Returns (text, ok)."""
    with open(path) as fh:
        t = fh.read()
    name = os.path.basename(path)
    ok = True
    labels = set(re.findall(r"\\label\{([^}]+)\}", t))
    refs = set(re.findall(r"\\ref\{([^}]+)\}", t))
    miss = refs - labels
    print(f"[{name}] refs without a label: {sorted(miss) if miss else 'NONE (ok)'}")
    if miss:
        ok = False
    if check_figs:
        for im in re.findall(r"\\includegraphics\[[^]]*\]\{([^}]+)\}", t):
            p = os.path.join(os.path.dirname(path), "figures", im)
            status = "OK" if os.path.exists(p) else "MISSING"
            print(f"[{name}] figure {im}: {status}")
            if status == "MISSING":
                ok = False
    bal = t.count("{") == t.count("}")
    print(f"[{name}] braces balanced: {bal} ({t.count('{')} open / {t.count('}')} close)")
    if not bal:
        ok = False
    return t, ok


def check_citations(main_text):
    """Every \\cite key resolves in references.bib (+ flag uncited entries). Returns ok."""
    with open(os.path.join(MAN, "references.bib")) as fh:
        bib = fh.read()
    cited = set()
    for grp in re.findall(r"\\cite[a-zA-Z]*\{([^}]+)\}", main_text):
        cited |= {k.strip() for k in grp.split(",")}
    defined = set(re.findall(r"@\w+\{\s*([^,\s]+)\s*,", bib))
    missing = cited - defined
    print(f"[cite] {len(cited)} cite keys, {len(defined)} bib entries")
    print(f"[cite] cited keys missing from references.bib: "
          f"{sorted(missing) if missing else 'NONE (all wired)'}")
    uncited = defined - cited
    print(f"[cite] bib entries never cited: {sorted(uncited) if uncited else 'NONE'}")
    return not missing


def check_toolvocab(path):
    """No toolchain vocabulary in author-facing prose. Returns ok."""
    with open(path) as fh:
        t = fh.read()
    name = os.path.basename(path)
    hits = []
    for pat in TOOLVOCAB:
        for m in re.finditer(pat, t):
            line = t[:m.start()].count("\n") + 1
            hits.append((line, m.group(0)))
    if hits:
        print(f"[{name}] TOOLCHAIN-VOCAB LEAK ({len(hits)}): " +
              ", ".join(f"L{ln}:{tok}" for ln, tok in hits[:20]))
        return False
    print(f"[{name}] tool-vocabulary: clean (names the science)")
    return True


def main():
    ok = True
    main_tex, t_ok = check_tex(os.path.join(MAN, "main.tex"))
    ok = ok and t_ok
    _, s_ok = check_tex(os.path.join(MAN, "si.tex"), check_figs=False)
    ok = ok and s_ok
    ok = check_citations(main_tex) and ok
    ok = check_toolvocab(os.path.join(MAN, "main.tex")) and ok
    ok = check_toolvocab(os.path.join(MAN, "si.tex")) and ok
    print("=" * 50)
    print("PACKAGE CHECK:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
