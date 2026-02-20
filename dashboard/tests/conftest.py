"""
conftest.py — pytest configuration for dashboard tests.
Adds the dashboard/ directory to sys.path so analytics can be imported directly.
"""
import sys
import os

# Ensure `dashboard/` is on the path so `import analytics` works from tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
