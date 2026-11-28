# SPDX-License-Identifier: Apache-2.0
# One-command entry points. Everything here must work on a clean machine with a
# Python 3.12+ interpreter and no network access.

PY ?= python

.PHONY: help install test lint hygiene validate site-check vectors bend-fetch all clean

help:
	@echo "make install     install the package in editable mode with dev extras"
	@echo "make test        run the unit tests (stdlib unittest)"
	@echo "make lint        ruff + mypy, if installed"
	@echo "make hygiene     secrets, licence headers, whitespace, oracle absence, DCO"
	@echo "make validate    validate schemas and task packages"
	@echo "make site-check  structural checks on the GitHub Pages site"
	@echo "make vectors     compile the fixture and run the L1 trace gate (needs bun)"
	@echo "make all         test + hygiene + validate + site-check"

install:
	$(PY) -m pip install -e ".[dev]"

test:
	$(PY) -m unittest discover -s tests -v

lint:
	-$(PY) -m ruff check .
	-$(PY) -m mypy bendeda

hygiene:
	$(PY) tools/check_secrets.py .
	$(PY) tools/check_license_headers.py .
	$(PY) tools/check_whitespace.py .
	$(PY) tools/check_links.py .
	$(PY) tools/check_oracle_absence.py .

validate:
	$(PY) -m bendeda validate --all

site-check:
	$(PY) tools/check_site.py site

bend-fetch:
	$(PY) tools/fetch_bend.py

vectors: bend-fetch
	$(PY) -m bendeda conformance compile 		--model experiments/fixtures/toy_counter/model.bend --out .bend-cache/out/model.mjs
	$(PY) -m bendeda conformance trace --module .bend-cache/out/model.mjs --cycles 24
	$(PY) -m bendeda conformance trace --module .bend-cache/out/model.mjs --cycles 24 --inject-offset 1

all: test hygiene validate site-check

clean:
	rm -rf .mypy_cache .ruff_cache build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
