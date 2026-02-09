# Makefile
# --------
# Usage:
# make [COMMAND]
# E.g.:
# make install
# make build

.PHONY: build clean test clean-pycache format install uninstall

SHELL := /usr/bin/env bash

install:
	@if [[ -n "$$VIRTUAL_ENV" ]]; then \
	    echo "Installing ExamMachine2QTI dependencies into virtual environment $$VIRTUAL_ENV"; \
	    pip install -U pip wheel; \
	    pip install -e .[dev]; \
	else \
	    echo "Not in a virtual environment, install one first and then try again."; \
	fi

uninstall:
	@if [[ -n "$$VIRTUAL_ENV" ]]; then \
	    echo "Uninstalling ExamMachine2QTI dependencies from virtual environment $$VIRTUAL_ENV"; \
	    pip uninstall GEMS; \

	else \
	    echo "Not in a virtual environment, nothing to uninstall."; \
	fi

format:
	ruff check exammachine2qti --fix
	ruff format exammachine2qti

build:
	python -m build

clean:
	rm -rf build dist *.egg-info

test:
	PYTHONPATH=$(shell pwd) pytest tests/
	PYTHONPATH=$(shell pwd) pytest tests/unittests/
	PYTHONPATH=$(shell pwd) pytest tests/guitests/

clean-pycache:
	find . -type d -name "__pycache__" -exec rm -rf {} +
