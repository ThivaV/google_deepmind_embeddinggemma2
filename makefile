# Run the apps.
#
#   make desktop             open the macOS desktop app
#   make streamlit-start     start the web app in the background and open it in the browser
#   make streamlit-stop      stop the web app
#
# `make` on its own lists every target. Settings can be changed per call, e.g.
#   make streamlit-start STREAMLIT_PORT=8502 OPEN=0
#
# Written for the GNU Make 3.81 that ships with macOS.

ROOT           := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
VENV           ?= $(ROOT).venv
PYTHON         := $(VENV)/bin/python
STREAMLIT      := $(VENV)/bin/streamlit
STREAMLIT_PORT ?= 8501
OPEN           ?= 1
LOGS           := $(ROOT)logs
PID_FILE       := $(LOGS)/streamlit.pid
LOG_FILE       := $(LOGS)/streamlit.log

SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help desktop streamlit-start streamlit-stop streamlit-restart streamlit-status streamlit-logs check-venv

# Reads "pid port" from PID_FILE, and keeps pid only if that process is still this web
# app -- so a stale file can never get some other program stopped.
RUNNING = read -r pid port 2>/dev/null < "$(PID_FILE)"; \
	ps -p "$$pid" -o command= 2>/dev/null | grep -q "streamlit run app.py" || pid=


help: ## List the targets
	@echo "Usage: make <target>"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-20s %s\n", $$1, $$2}'
	@echo
	@echo "Options: STREAMLIT_PORT=8501 (web app port), OPEN=0 (don't open the browser), VENV=path"


desktop: check-venv ## Open the macOS desktop app (it quits when you close its window)
	@cd "$(ROOT)" && "$(PYTHON)" src/customtkinter/app.py


streamlit-start: check-venv ## Start the web app in the background and open it in the browser
	@mkdir -p "$(LOGS)"
	@$(RUNNING); \
	if [ -n "$$pid" ]; then echo "Already running at http://localhost:$$port (pid $$pid)."; exit 0; fi; \
	if lsof -nP -iTCP:$(STREAMLIT_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
	    echo "Port $(STREAMLIT_PORT) is taken by another program. Try: make streamlit-start STREAMLIT_PORT=8502"; \
	    exit 1; \
	fi; \
	echo "Starting the web app on port $(STREAMLIT_PORT)…"; \
	( cd "$(ROOT)src/streamlit" && exec nohup "$(STREAMLIT)" run app.py \
	    --server.headless true --server.port $(STREAMLIT_PORT) ) > "$(LOG_FILE)" 2>&1 & \
	pid=$$!; echo "$$pid $(STREAMLIT_PORT)" > "$(PID_FILE)"; \
	url="http://localhost:$(STREAMLIT_PORT)"; \
	for i in $$(seq 60); do \
	    if ! kill -0 $$pid 2>/dev/null; then \
	        echo "The web app stopped while starting. The end of its log:"; \
	        tail -n 20 "$(LOG_FILE)"; rm -f "$(PID_FILE)"; exit 1; \
	    fi; \
	    curl -fs "$$url/_stcore/health" >/dev/null 2>&1 && break; \
	    sleep 1; \
	done; \
	if ! curl -fs "$$url/_stcore/health" >/dev/null 2>&1; then \
	    echo "Started (pid $$pid) but not answering yet. Watch it with: make streamlit-logs"; exit 0; \
	fi; \
	echo "Running at $$url (pid $$pid). Stop it with: make streamlit-stop"; \
	if [ "$(OPEN)" = 1 ]; then open "$$url"; fi


streamlit-stop: ## Stop the web app
	@$(RUNNING); \
	if [ -z "$$pid" ]; then echo "The web app isn't running."; rm -f "$(PID_FILE)"; exit 0; fi; \
	kill $$pid; \
	for i in $$(seq 20); do kill -0 $$pid 2>/dev/null || break; sleep 0.5; done; \
	if kill -0 $$pid 2>/dev/null; then kill -9 $$pid; fi; \
	rm -f "$(PID_FILE)"; \
	echo "Stopped the web app (pid $$pid)."


streamlit-restart: ## Stop the web app, then start it again
	@$(MAKE) --no-print-directory streamlit-stop
	@$(MAKE) --no-print-directory streamlit-start


streamlit-status: ## Show whether the web app is running, and where
	@$(RUNNING); \
	if [ -z "$$pid" ]; then echo "The web app isn't running."; \
	elif curl -fs "http://localhost:$$port/_stcore/health" >/dev/null 2>&1; then \
	    echo "Running at http://localhost:$$port (pid $$pid)."; \
	else echo "Running (pid $$pid) but not answering at http://localhost:$$port. See: make streamlit-logs"; fi


streamlit-logs: ## Follow the web app's log (Ctrl+C stops following, not the app)
	@if [ -f "$(LOG_FILE)" ]; then tail -n 50 -f "$(LOG_FILE)"; else echo "No log yet: start the web app first."; fi


check-venv:
	@if [ ! -x "$(PYTHON)" ] || [ ! -x "$(STREAMLIT)" ]; then \
	    echo "No virtualenv with the apps' packages at $(VENV). Set it up with:"; \
	    echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt"; \
	    exit 1; \
	fi
