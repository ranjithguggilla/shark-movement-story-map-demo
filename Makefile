PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
RUN := $(VENV)/bin/python
STREAMLIT := $(VENV)/bin/streamlit

.PHONY: help setup run build-outputs smoke clean

help:
	@echo "Targets:"
	@echo "  setup          - Create virtualenv and install requirements"
	@echo "  build-outputs  - Regenerate track metrics and sample story summaries"
	@echo "  run            - Run Streamlit app locally"
	@echo "  smoke          - Run non-UI smoke checks"
	@echo "  clean          - Remove virtualenv and python caches"

setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

build-outputs:
	$(RUN) -m src.track_metrics
	$(RUN) -m src.story_generator

run:
	$(STREAMLIT) run app.py

smoke:
	$(RUN) scripts/smoke_test.py

clean:
	rm -rf $(VENV) .venv_scratch __pycache__ src/__pycache__
