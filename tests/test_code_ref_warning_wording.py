"""Render warnings word a changed data file as data, not as an unshipped script.

Found by the final check of the trial-2 fixes (2026-10-10): a data file named in a
code_ref whose hash changed was reported with the script suffix "it was not shipped as
the reproduction script (kept as a pointer)".
"""

from __future__ import annotations

from sci_adk import cli


class _Compiler:
    def __init__(self, scripts, data):
        self.code_ref_warnings = list(scripts) + list(data)
        self.code_ref_data_warnings = list(data)


def test_data_file_mismatch_is_worded_as_data(capsys):
    data = "evi-x: code_ref names data file analysis/d.csv with sha256=aa, but that file now hashes to bb"
    cli._print_code_ref_warnings(_Compiler([], [data]))
    err = capsys.readouterr().err
    assert "analysis/d.csv" in err
    assert "restored" in err
    assert "reproduction script" not in err


def test_script_mismatch_keeps_the_script_wording(capsys):
    script = "evi-y: code_ref names analysis/s.py with sha256=aa, but that file now hashes to bb"
    cli._print_code_ref_warnings(_Compiler([script], []))
    err = capsys.readouterr().err
    assert "reproduction script" in err
