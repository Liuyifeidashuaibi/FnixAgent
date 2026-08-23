# Makefile with uv binary path fix

# Export UV_BIN to make it available to recursive make calls
export UV_BIN ?= $(shell command -v uv 2>/dev/null || echo "$(HOME)/.local/bin/uv")

.PHONY: install-dev
default: install-dev

install-dev:
	@echo "Installing development dependencies with uv"
	@$(UV_BIN) pip install -e .[dev]

.PHONY: detect-secrets-scan
detect-secrets-scan:
	@echo "Running detect-secrets scan"
	@$(UV_BIN) pip install detect-secrets
	@detect-secrets scan --baseline .secrets.baseline

.PHONY: test
test:
	@echo "Running tests"
	@$(UV_BIN) pip install pytest pytest-cov
	@pytest --cov=mcpgateway --cov-report=html --cov-report=term-missing

.PHONY: lint
lint:
	@echo "Running linting"
	@$(UV_BIN) pip install pylint ruff
	@pylint mcpgateway
	@ruff check mcpgateway

.PHONY: format
format:
	@echo "Running code formatting"
	@$(UV_BIN) pip install black isort
	@black mcpgateway
	@isort mcpgateway

.PHONY: security
security:
	@echo "Running security scan"
	@$(UV_BIN) pip install bandit
	@bandit -r mcpgateway

.PHONY: docs
docs:
	@echo "Building documentation"
	@$(UV_BIN) pip install sphinx
	@sphinx-build -b html docs docs/_build/html

.PHONY: clean
clean:
	@echo "Cleaning build artifacts"
	@rm -rf docs/_build
	@rm -rf mcpgateway.egg-info
	@rm -f .coverage
	@rm -f .secrets.baseline

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  install-dev     - Install development dependencies"
	@echo "  detect-secrets-scan - Run detect-secrets scan"
	@echo "  test          - Run tests with coverage"
	@echo "  lint          - Run linting tools"
	@echo "  format        - Format code"
	@echo "  security      - Run security scan"
	@echo "  docs          - Build documentation"
	@echo "  clean         - Clean build artifacts"
	@echo "  help          - Show this help message"
