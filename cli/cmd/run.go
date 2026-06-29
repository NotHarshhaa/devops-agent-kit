package cmd

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

// Supported agents and brains.
var (
	validAgents = []string{"drift-detector", "deploy-reviewer", "infra-monitor"}
	validBrains = []string{"autogen", "langgraph"}
)

// Run-specific flags.
var (
	agentName    string
	brainName    string
	interval     string
	pipelinePath string
)

// PipelineConfig maps the pipeline YAML configuration.
type PipelineConfig struct {
	Pipeline struct {
		Name        string   `yaml:"name"`
		Description string   `yaml:"description"`
		Agent       string   `yaml:"agent"`
		Brain       string   `yaml:"brain"`
		Namespace   string   `yaml:"namespace"`
		Namespaces  []string `yaml:"namespaces"`
		Interval    string   `yaml:"interval"`
		ArgoCD      *struct {
			Server   string `yaml:"server"`
			Insecure bool   `yaml:"insecure"`
		} `yaml:"argocd"`
		Prometheus *struct {
			URL string `yaml:"url"`
		} `yaml:"prometheus"`
		Notifications *struct {
			Slack *struct {
				Enabled bool   `yaml:"enabled"`
				Channel string `yaml:"channel"`
			} `yaml:"slack"`
		} `yaml:"notifications"`
	} `yaml:"pipeline"`
}

// runCmd represents the "run" command.
var runCmd = &cobra.Command{
	Use:   "run",
	Short: "Run an agent with a specified brain and tool bindings",
	Long: `Run starts a DevOps AI agent using the specified brain (AutoGen or LangGraph).

The agent will use tool bindings for Kubernetes, ArgoCD, and Prometheus
to reason over your infrastructure state. Alternatively, you can specify
a pipeline configuration YAML file.

Examples:
  devops-agent run --agent drift-detector --brain autogen
  devops-agent run --pipeline orchestration/pipelines/argocd-agent.yaml
  devops-agent run --agent deploy-reviewer --brain langgraph --namespace production
  devops-agent run --agent infra-monitor --brain autogen --interval 10m`,
	RunE: runAgent,
}

func init() {
	runCmd.Flags().StringVar(&agentName, "agent", "", "Agent to run (drift-detector | deploy-reviewer | infra-monitor)")
	runCmd.Flags().StringVar(&brainName, "brain", "", "Agent brain to use (autogen | langgraph)")
	runCmd.Flags().StringVar(&interval, "interval", "", "Polling interval for continuous agents (e.g. 5m)")
	runCmd.Flags().StringVarP(&pipelinePath, "pipeline", "p", "", "Path to pipeline YAML configuration")

	rootCmd.AddCommand(runCmd)
}

// resolvePython finds the first available Python interpreter in the PATH.
func resolvePython() (string, error) {
	if path, err := exec.LookPath("python3"); err == nil {
		return path, nil
	}
	if path, err := exec.LookPath("python"); err == nil {
		return path, nil
	}
	return "", fmt.Errorf("neither 'python3' nor 'python' was found in PATH")
}

// runAgent validates inputs and launches the selected agent via Python.
func runAgent(cmd *cobra.Command, args []string) error {
	// If pipeline config is provided, parse and apply its settings
	if pipelinePath != "" {
		data, err := os.ReadFile(pipelinePath)
		if err != nil {
			return fmt.Errorf("failed to read pipeline file: %w", err)
		}
		var cfg PipelineConfig
		if err := yaml.Unmarshal(data, &cfg); err != nil {
			return fmt.Errorf("failed to parse pipeline YAML: %w", err)
		}

		if !cmd.Flags().Changed("agent") && cfg.Pipeline.Agent != "" {
			agentName = cfg.Pipeline.Agent
		}
		if !cmd.Flags().Changed("brain") && cfg.Pipeline.Brain != "" {
			brainName = cfg.Pipeline.Brain
		}
		if !cmd.Flags().Changed("interval") && cfg.Pipeline.Interval != "" {
			interval = cfg.Pipeline.Interval
		}
		if !cmd.Flags().Changed("namespace") {
			if cfg.Pipeline.Namespace != "" {
				namespace = cfg.Pipeline.Namespace
			} else if len(cfg.Pipeline.Namespaces) > 0 {
				namespace = cfg.Pipeline.Namespaces[0]
			}
		}

		// Set environment variables for tool bindings if defined in pipeline
		if cfg.Pipeline.ArgoCD != nil {
			if cfg.Pipeline.ArgoCD.Server != "" {
				os.Setenv("ARGOCD_SERVER", cfg.Pipeline.ArgoCD.Server)
			}
			if cfg.Pipeline.ArgoCD.Insecure {
				os.Setenv("ARGOCD_INSECURE", "true")
			} else {
				os.Setenv("ARGOCD_INSECURE", "false")
			}
		}
		if cfg.Pipeline.Prometheus != nil && cfg.Pipeline.Prometheus.URL != "" {
			os.Setenv("PROMETHEUS_URL", cfg.Pipeline.Prometheus.URL)
		}
	}

	// Validate agent name
	if agentName == "" {
		return fmt.Errorf("missing agent — specify --agent or define in pipeline YAML")
	}
	if !contains(validAgents, agentName) {
		return fmt.Errorf("unknown agent %q — valid agents: %s", agentName, strings.Join(validAgents, ", "))
	}

	// Validate brain name
	if brainName == "" {
		return fmt.Errorf("missing brain — specify --brain or define in pipeline YAML")
	}
	if !contains(validBrains, brainName) {
		return fmt.Errorf("unknown brain %q — valid brains: %s", brainName, strings.Join(validBrains, ", "))
	}

	// Resolve python interpreter
	pyBin, err := resolvePython()
	if err != nil {
		return err
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
	if pipelinePath != "" {
		absPath, err := filepath.Abs(pipelinePath)
		if err == nil {
			pyArgs = append(pyArgs, "--pipeline", absPath)
		} else {
			pyArgs = append(pyArgs, "--pipeline", pipelinePath)
		}
	}

	// Print launch info
	fmt.Printf("🤖 devops-agent — launching agent\n")
	fmt.Printf("   Agent:      %s\n", agentName)
	fmt.Printf("   Brain:      %s\n", brainName)
	fmt.Printf("   Namespace:  %s\n", namespace)
	if interval != "" {
		fmt.Printf("   Interval:   %s\n", interval)
	}
	if pipelinePath != "" {
		fmt.Printf("   Pipeline:   %s\n", pipelinePath)
	}
	if dryRun {
		fmt.Printf("   Mode:       dry-run\n")
	}
	fmt.Println()

	if verbose {
		fmt.Printf("   Command:    %s %s\n\n", pyBin, strings.Join(pyArgs, " "))
	}

	// Execute the agent
	pyCmd := exec.Command(pyBin, pyArgs...)
	pyCmd.Stdout = os.Stdout
	pyCmd.Stderr = os.Stderr
	pyCmd.Stdin = os.Stdin
	pyCmd.Dir = root
	pyCmd.Env = append(os.Environ(), "PYTHONUNBUFFERED=1")

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
