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
# A verbatim copy of the lists the package gate itself applies (sci_adk.render.paper:
# _PAPER_TOOL_PHRASES, _PAPER_TOOL_WORD_RE, _PAPER_TOOL_PROPER_RE, _PAPER_ARTIFACT_RES), so a
# reviewer re-running this script gets the gate's answer; sci-adk's test suite fails when the
# copies differ. Only compounds that name the authoring machinery are listed: the bare phrase
# "decision rule" is standard statistics, and "Evidence", "Claim" and "verify" are ordinary
# English.
TOOL_PHRASES = (
    "sci-adk",
    "frozen spec",
    "engine-derived",
    "the engine",
    "verify audit",
    "append-only",
    "evidence record",
    "belief state",
    "anti-harking",
    "result.point",
    "result.finding",
    "claim status",
    "evidence item",
    "record digest",
    "spec digest",
    "record fidelity",
    "frozen contract",
    "frozen decision rule",
    "pre-registered decision rule",
    "research compiler",
    "verify gate",
)
# A paper states a "result", not a "verdict".
TOOL_WORD_RE = re.compile(r"\b(?:verdict|verdicts)\b", re.IGNORECASE)
# "Spec" as the tool's proper noun; "specification" and lowercase "spec" are fine.
TOOL_PROPER_RE = re.compile(r"\bSpec\b")
# Run-artifact ids (by shape) and internal artifact file/directory names (any case).
ARTIFACT_RES = (
    re.compile(r"\bevi-[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"),
    re.compile(r"\bclaim-(?:hyp|novelty)-[A-Za-z0-9._-]*[A-Za-z0-9]"),
    re.compile(
        r"\b(?:spec|pubreqs|pkgreqs|declarations|review|numbers(?:\.draft)?)\.json\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bnovelty(?:\\_|_)sentences\.json\b", re.IGNORECASE),
    re.compile(r"\bspec\.v\d+\.json\b", re.IGNORECASE),
    re.compile(r"\bspec(?:\\_|_)history\b", re.IGNORECASE),
    re.compile(r"\b(?:checkpoints|science)\.md\b", re.IGNORECASE),
)


def toolvocab_hits(text):
    """(term, offset of its first occurrence) for each toolchain term in ``text``, in the
    order the package gate reports them (sci_adk.render.paper.check_paper_tool_vocabulary)."""
    low = text.lower()
    hits = []
    seen = set()

    def add(term, offset):
        if term not in seen:
            seen.add(term)
            hits.append((term, offset))

    for phrase in TOOL_PHRASES:
        at = low.find(phrase)
        if at >= 0:
            add(phrase, at)
    for m in TOOL_WORD_RE.finditer(text):
        add(m.group(0).lower(), m.start())
    m = TOOL_PROPER_RE.search(text)
    if m:
        add("Spec", m.start())
    for pattern in ARTIFACT_RES:
        for m in pattern.finditer(text):
            add(m.group(0), m.start())
    return hits


def toolvocab_leaks(text):
    """The distinct toolchain terms in ``text`` -- the package gate's answer."""
    return [term for term, _ in toolvocab_hits(text)]


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
    hits = [(t[:at].count("\n") + 1, term) for term, at in toolvocab_hits(t)]
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
