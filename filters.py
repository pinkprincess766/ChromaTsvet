"""Compatibility alias for the packaged analysis filters module."""

from __future__ import annotations

import sys

from python_analyzer.analysis import filters as _filters

sys.modules[__name__] = _filters
