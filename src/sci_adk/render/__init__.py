"""
sci-adk render: Claims + Evidence -> paper draft.

Deterministic Markdown rendering (no LLM, zero cost). Prose polishing is a
separate in-session agent step, never an autonomous LLM call.
"""

from sci_adk.render.paper import render_paper

__all__ = ["render_paper"]
