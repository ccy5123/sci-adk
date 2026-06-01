"""
Pytest configuration for sci-adk tests.

Automatically imports all fixtures from fixtures.py to make them available
to all test modules.
"""

from tests.fixtures import *  # noqa: F401, F403
