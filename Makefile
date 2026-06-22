.PHONY: init build run-drift run-deploy run-monitor status update-subs clean help

BINARY   := devops-agent
BUILD_DIR := bin
CLI_DIR  := cli

# ── Submodules ──────────────────────────────────────────────

init: ## Initialize all Git submodules
	git submodule update --init --recursive

update-subs: ## Pull latest commits for all submodules
	git submodule update --remote --merge

# ── Build ───────────────────────────────────────────────────

build: ## Build the Go CLI binary
	@mkdir -p $(BUILD_DIR)
	cd $(CLI_DIR) && go build -o ../$(BUILD_DIR)/$(BINARY) .
	@echo "Built $(BUILD_DIR)/$(BINARY)"

# ── Run Agents ──────────────────────────────────────────────

run-drift: build ## Run drift-detector with AutoGen
	./$(BUILD_DIR)/$(BINARY) run --agent drift-detector --brain autogen

run-deploy: build ## Run deploy-reviewer with LangGraph
	./$(BUILD_DIR)/$(BINARY) run --agent deploy-reviewer --brain langgraph

run-monitor: build ## Run infra-monitor with AutoGen (5m interval)
	./$(BUILD_DIR)/$(BINARY) run --agent infra-monitor --brain autogen --interval 5m

# ── Status ──────────────────────────────────────────────────

status: build ## Check tool bindings health
	./$(BUILD_DIR)/$(BINARY) status

# ── Clean ───────────────────────────────────────────────────

clean: ## Remove build artifacts
	rm -rf $(BUILD_DIR)
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned build artifacts"

# ── Help ────────────────────────────────────────────────────

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
