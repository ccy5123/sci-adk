"""
Vocabulary check on deposit names (design/deposit-files.md D6, test plan item 13).

The reader-facing names of the deposited files pass; the internal checkpoint files and the
author's declaration fail, in any letter case. ``checkpoints/`` alone is not banned: a
paper may deposit a folder of model checkpoints.
"""

from __future__ import annotations

import pytest

from sci_adk.render.paper import check_paper_tool_vocabulary


@pytest.mark.parametrize("text", [
    "deposit/protocol/protocol-v1.json",
    "deposit/protocol/amendment-v2.json",
    "deposit/data/chemicals.csv",
    "deposit/manifest.csv",
    r"06\_provenance/protocol/SPEC-BCFKOW-001/protocol-v1.json",
    r"02\_data/SPEC-BCFKOW-001/chemicals.csv",
    r"06\_provenance/deposit.csv",
    "checkpoints/config.json",
    "the weights are in checkpoints/ beside the code",
    "zenodo.org/deposit/1.json",
])
def test_reader_facing_names_pass(text):
    assert check_paper_tool_vocabulary(text) == []


@pytest.mark.parametrize("text", [
    "spec.json", "SPEC.JSON", "numbers.json", "declarations.json", "evi-obs-1",
    "spec.v1.json", "SPEC.V1.JSON", "spec_history/spec.v1.json", r"spec\_history/spec.v1.json",
    "spec_history/", r"the spec\_history folder", "Spec_History/",
])
def test_names_flagged_before_stay_flagged(text):
    assert check_paper_tool_vocabulary(text)


@pytest.mark.parametrize("text", [
    "checkpoints/amendment-v2.json",
    "checkpoints/prior_work.json",
    r"checkpoints/prior\_work.json",
    "checkpoints/science.json",
    "Checkpoints/Science.json",
    "deposit.json",
    "Deposit.json",
])
def test_internal_checkpoint_files_and_the_declaration_are_flagged(text):
    assert check_paper_tool_vocabulary(f"The file {text} holds it.")
