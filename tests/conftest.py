"""Tests explicitly opt into the fixture/demo adapter used by legacy workflow tests."""
import os

os.environ.setdefault("DEMO_MODE_ENABLED", "true")
