PYTHON ?= python3

.PHONY: help setup doctor run test rust check

help:
	@$(PYTHON) scripts/dev.py --help

setup:
	$(PYTHON) scripts/dev.py setup

doctor:
	$(PYTHON) scripts/dev.py doctor

run:
	$(PYTHON) scripts/dev.py run

test:
	$(PYTHON) scripts/dev.py test

rust:
	$(PYTHON) scripts/dev.py rust

check: test rust
