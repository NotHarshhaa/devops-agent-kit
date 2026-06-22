package cmd

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
)

// Supported agents and brains.
var (
	validAgents = []string{"drift-detector", "deploy-reviewer", "infra-monitor"}
	validBrains = []string{"autogen", "langgraph"}
)

// Run-specific flags.
var (
	agentName string
	brainName string
	interval  string
)

// runCmd represents the "run" command.
var runCmd = &cobra.Command{
	Use:   "run",
	Short: "Run an agent with a specified brain and tool bindings",
	Long: `Run starts a DevOps AI agent using the specified brain (AutoGen or LangGraph).

The agent will use tool bindings for Kubernetes, ArgoCD, and Prometheus
to reason over your infrastructure state.

Examples:
  devops-agent run --agent drift-detector --brain autogen
  devops-agent run --agent deploy-reviewer --brain langgraph --namespace production
  devops-agent run --agent infra-monitor --brain autogen --interval 10m`,
	RunE: runAgent,
}

func init() {
	runCmd.Flags().StringVar(&agentName, "agent", "", "Agent to run (drift-detector | deploy-reviewer | infra-monitor)")
	runCmd.Flags().StringVar(&brainName, "brain", "", "Agent brain to use (autogen | langgraph)")
	runCmd.Flags().StringVar(&interval, "interval", "", "Polling interval for continuous agents (e.g. 5m)")

	_ = runCmd.MarkFlagRequired("agent")
	_ = runCmd.MarkFlagRequired("brain")

	rootCmd.AddCommand(runCmd)
}

// runAgent validates inputs and launches the selected agent via Python.
func runAgent(cmd *cobra.Command, args []string) error {
	// Validate agent name
	if !contains(validAgents, agentName) {
		return fmt.Errorf("unknown agent %q — valid agents: %s", agentName, strings.Join(validAgents, ", "))
	}

	// Validate brain name
	if !contains(validBrains, brainName) {
		return fmt.Errorf("unknown brain %q — valid brains: %s", brainName, strings.Join(validBrains, ", "))
	}

	// Resolve project root and agent script path
	root, err := projectRoot()
	if err != nil {
		return fmt.Errorf("cannot determine project root: %w", err)
	}

	agentScript := filepath.Join(root, "agents", agentName+"-agent.py")
	if _, err := os.Stat(agentScript); os.IsNotExist(err) {
		return fmt.Errorf("agent script not found: %s", agentScript)
	}

	configFile := filepath.Join(root, "orchestration", "configs", brainName+"-config.yaml")
	if _, err := os.Stat(configFile); os.IsNotExist(err) {
		return fmt.Errorf("brain config not found: %s", configFile)
	}

	// Build the Python command
	pyArgs := []string{
		agentScript,
		"--brain", brainName,
		"--config", configFile,
		"--namespace", namespace,
	}

	if interval != "" {
		pyArgs = append(pyArgs, "--interval", interval)
	}
	if dryRun {
		pyArgs = append(pyArgs, "--dry-run")
	}
	if verbose {
		pyArgs = append(pyArgs, "--verbose")
	}

	// Print launch info
	fmt.Printf("🤖 devops-agent — launching agent\n")
	fmt.Printf("   Agent:     %s\n", agentName)
	fmt.Printf("   Brain:     %s\n", brainName)
	fmt.Printf("   Namespace: %s\n", namespace)
	if interval != "" {
		fmt.Printf("   Interval:  %s\n", interval)
	}
	if dryRun {
		fmt.Printf("   Mode:      dry-run\n")
	}
	fmt.Println()

	// Execute the agent
	pyCmd := exec.Command("python3", pyArgs...)
	pyCmd.Stdout = os.Stdout
	pyCmd.Stderr = os.Stderr
	pyCmd.Stdin = os.Stdin
	pyCmd.Dir = root

	if err := pyCmd.Run(); err != nil {
		return fmt.Errorf("agent exited with error: %w", err)
	}

	return nil
}

// contains checks if a string is in a slice.
func contains(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}
