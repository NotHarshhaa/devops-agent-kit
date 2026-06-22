// Package cmd implements all CLI commands for devops-agent.
//
// The root command sets up global flags shared across subcommands
// and provides the top-level help text.
package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

// Global flags shared by all subcommands.
var (
	verbose   bool
	namespace string
	dryRun    bool
)

// rootCmd is the base command when called without any subcommands.
var rootCmd = &cobra.Command{
	Use:   "devops-agent",
	Short: "AI-powered DevOps automation CLI",
	Long: `devops-agent — A modular agentic AI toolkit for DevOps automation.

Bring AI-powered reasoning to your Kubernetes, ArgoCD, and Prometheus
workflows with pluggable tool bindings and dual agent brains
(AutoGen + LangGraph).

Use "devops-agent [command] --help" for more information about a command.`,
}

// Execute runs the root command. Called from main().
func Execute() error {
	return rootCmd.Execute()
}

func init() {
	rootCmd.PersistentFlags().BoolVarP(&verbose, "verbose", "v", false, "Enable verbose output")
	rootCmd.PersistentFlags().StringVarP(&namespace, "namespace", "n", "default", "Kubernetes namespace to target")
	rootCmd.PersistentFlags().BoolVar(&dryRun, "dry-run", false, "Preview agent actions without executing")
}

// projectRoot walks up from the binary location to find the project root.
// It looks for the "agents" directory as a marker.
func projectRoot() (string, error) {
	// Try current working directory first
	cwd, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("failed to get working directory: %w", err)
	}

	// Check if agents/ exists relative to cwd (repo root)
	if _, err := os.Stat(fmt.Sprintf("%s/agents", cwd)); err == nil {
		return cwd, nil
	}

	// Check parent (for when running from bin/)
	parent := fmt.Sprintf("%s/..", cwd)
	if _, err := os.Stat(fmt.Sprintf("%s/agents", parent)); err == nil {
		return parent, nil
	}

	return cwd, nil
}
