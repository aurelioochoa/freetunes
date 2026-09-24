# The standard Makefile.
#
# Copy this into a project, fill in the identity header, then replace each verb
# below with that stack's real command. Every repo answers the same eleven
# verbs, so `make` in any of them lists the same vocabulary.
#
#   help  setup  dev  build  run  test  check  verify  fmt  clean  distclean
#
# Rules that keep the set uniform:
#
#   * `make` on its own always prints the help. It never builds, installs or
#     starts anything.
#   * A verb that does not apply still EXISTS and explains why, via $(call NA,
#     '...'). A missing target gives make's "No rule to make target", which
#     reads like a broken Makefile rather than an answer.
#   * `check` is the fast gate and `verify` is `check` plus a build.
#   * `clean` is always safe to run. Anything that costs a reinstall — node_
#     modules, .venv, target/, docker volumes — belongs to `distclean`.
#   * A project's own targets keep their own `##@ Section`. Renaming one breaks
#     the docs, so the old name stays as an alias with no `##` comment, which
#     keeps it out of the help.
#
# The block between the two sentinels is byte-identical in every repo, so
# checking for drift is a diff and needs no parser.

# ─── Identity (the only part that differs between repos) ─────────────────────
# No apostrophes in any of these four: they are interpolated into a
# single-quoted shell string in the help recipe.
PROJECT       := freetunes
TAGLINE       := FOSS web iTunes clone for iPhone media
# `=` and not `:=`: with `:=` these expand before the variables they cite are
# defined further down, and the help footer prints empty values with no error.
HELP_VARS      = PORT=$(PORT) UI_PORT=$(UI_PORT) FREETUNES_MOCK=$(FREETUNES_MOCK) FREETUNES_LOG_LEVEL=$(FREETUNES_LOG_LEVEL)
HELP_EXAMPLE   = make dev FREETUNES_MOCK=1

# ─── Preamble ────────────────────────────────────────────────────────────────
# -e stops a recipe at the first failing command; -o pipefail stops a gate that
# pipes through a filter from reporting the filter's exit code instead of the
# command's — without it, a suite that fails into `tail` "passes".
SHELL         := /usr/bin/env bash
.SHELLFLAGS   := -eo pipefail -c
.DEFAULT_GOAL := help
MAKEFLAGS     += --no-print-directory

# ─── Colour ──────────────────────────────────────────────────────────────────
# MAKE_TERMOUT (GNU Make >= 4.1) is set only when stdout is a terminal, and is
# the only reliable test available here: `test -t 1` inside $(shell ...) always
# reports false, because make captures that command's stdout through a pipe.
# So `make help | less` and CI logs stay clean. NO_COLOR disables, FORCE_COLOR
# overrides both.
COLOR ?= $(if $(MAKE_TERMOUT),1,0)
ifdef NO_COLOR
  COLOR := 0
endif
ifdef FORCE_COLOR
  COLOR := 1
endif
ifeq ($(COLOR),1)
  # Real ESC bytes, so a plain `echo` renders them without needing -e.
  C_HEAD := $(shell printf '\033[1m')
  C_CMD  := $(shell printf '\033[36m')
  C_OK   := $(shell printf '\033[32m')
  C_WARN := $(shell printf '\033[33m')
  C_ERR  := $(shell printf '\033[31m')
  C_DIM  := $(shell printf '\033[2m')
  C_OFF  := $(shell printf '\033[0m')
endif

# Explains why a core verb does not apply here, then fails.
NA = @printf '  $(C_ERR)make $@$(C_OFF) does not apply to $(PROJECT).\n  $(C_DIM)%s$(C_OFF)\n\n' $(1) >&2; exit 2

# Width of the target-name column in help; widen it where names are long.
HELP_PAD ?= 18

# PROJECT, TAGLINE, HELP_VARS and HELP_EXAMPLE are interpolated into a
# single-quoted shell string below, so none of them may contain an apostrophe.
##@ General
.PHONY: help
help: ## List the available targets
	@printf '\n  $(C_HEAD)$(PROJECT)$(C_OFF) — $(TAGLINE)\n'
	@printf '  $(C_DIM)usage: make <target>$(C_OFF)\n'
	@awk 'BEGIN { FS = ":.*?## " } \
	  /^##@ / { printf "\n  $(C_HEAD)%s$(C_OFF)\n", substr($$0, 5); next } \
	  /^[a-zA-Z0-9_.-]+:.*?## / { printf "    $(C_CMD)%-$(HELP_PAD)s$(C_OFF) %s\n", $$1, $$2 }' \
	  $(MAKEFILE_LIST)
	@printf '\n  $(C_DIM)Variables:$(C_OFF) $(HELP_VARS)\n'
	@printf '  $(C_DIM)Example:$(C_OFF)   $(HELP_EXAMPLE)\n\n'

# ─── End of the shared block ─────────────────────────────────────────────────

PORT ?= 8000
UI_PORT ?= 5173
FREETUNES_MOCK ?= 0
FREETUNES_LOG_LEVEL ?= info

PY      := backend/.venv/bin/python
PIP     := backend/.venv/bin/pip
UVICORN := backend/.venv/bin/uvicorn

##@ Setup
.PHONY: setup
setup: install-backend install-frontend ## First run on a fresh clone: dependencies and local config

##@ Development
.PHONY: dev
dev: ## The fast iteration loop: backend :8000 + UI :5173 with live reload
	FREETUNES_MOCK=$(FREETUNES_MOCK) ./scripts/dev.sh

.PHONY: build
build: ## Produce the production artifact (frontend dist)
	cd frontend && pnpm build

.PHONY: run
run: ## Serve the production build: backend plus frontend preview
	(cd backend && FREETUNES_MOCK=$(FREETUNES_MOCK) .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $(PORT) --timeout-graceful-shutdown 5) & \
	(cd frontend && pnpm exec vite preview --host 127.0.0.1 --port $(UI_PORT)) & \
	wait

##@ Gates
.PHONY: test
test: ## Run the backend pytest suite
	$(PY) -m pytest -q backend

.PHONY: check
check: test check-frontend ## Fast gate: pytest plus frontend typecheck

.PHONY: verify
verify: check build ## Full gate: check, then a production build

.PHONY: fmt
fmt: ## Format the tree in place
	$(call NA,'No formatter configured: ruff/black/prettier are not in backend/requirements.txt or frontend/package.json.')

##@ Cleaning
.PHONY: clean
clean: ## Remove build output and test artifacts, never user data
	rm -rf backend/__pycache__ backend/app/__pycache__ backend/app/*/__pycache__ backend/tests/__pycache__ backend/.pytest_cache
	rm -rf frontend/dist

.PHONY: distclean
distclean: clean ## clean, plus installed dependencies (.venv, node_modules)
	rm -rf backend/.venv frontend/node_modules

##@ Project
.PHONY: install-backend install-frontend dev-backend dev-frontend check-backend check-frontend
install-backend: ## Create backend .venv and install Python deps
	python3 -m venv backend/.venv
	$(PIP) install -q -r backend/requirements.txt

install-frontend: ## Install frontend JS deps
	cd frontend && pnpm approve-builds esbuild && pnpm install

dev-backend: ## Run FastAPI with live reload on :8000 (FREETUNES_MOCK=1 forces mock)
	cd backend && FREETUNES_MOCK=$(FREETUNES_MOCK) .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $(PORT) --reload --log-level $(FREETUNES_LOG_LEVEL) --timeout-graceful-shutdown 5

dev-frontend: ## Run the Vite UI with live reload on :5173
	cd frontend && pnpm dev -- --host 127.0.0.1 --port $(UI_PORT)

check-backend: ## Run the backend pytest suite (same as make test)
	$(PY) -m pytest -q backend

check-frontend: ## Typecheck the frontend (tsc --noEmit)
	cd frontend && pnpm exec tsc --noEmit

.PHONY: setup-valeria-linux
setup-valeria-linux: ## Linux one-time USB setup for QuickTime (usbmuxd fork, needs sudo)
	bash scripts/setup-valeria-linux.sh

# ─── Compatibility aliases ───────────────────────────────────────────────────
# Any name the standard renamed, kept working because the docs still use it.
# No `##` comment, so these stay out of `make help`.
.PHONY: typecheck
typecheck: check-frontend
