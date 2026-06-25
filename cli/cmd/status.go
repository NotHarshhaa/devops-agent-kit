package cmd

import (
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

// statusCmd represents the "status" command.
var statusCmd = &cobra.Command{
	Use:   "status",
	Short: "Check health of connected tool bindings",
	Long: `Status checks connectivity to the infrastructure endpoints used by
tool bindings: Kubernetes API, ArgoCD server, and Prometheus.

Examples:
  devops-agent status
  devops-agent status --verbose`,
	RunE: checkStatus,
}

func init() {
	rootCmd.AddCommand(statusCmd)
}

// checkPythonEnvironment checks Python interpreter and library presence.
func checkPythonEnvironment() bool {
	fmt.Print("  Python Environment ... ")
	pyBin, err := resolvePython()
	if err != nil {
		fmt.Println("❌ Python not found in PATH")
		return false
	}

	// Get Python version
	versionBytes, err := exec.Command(pyBin, "--version").CombinedOutput()
	versionStr := "unknown version"
	if err == nil {
		versionStr = strings.TrimSpace(string(versionBytes))
	}

	// Run package checks
	pkgScript := `
import importlib
packages = {
	"kubernetes": "kubernetes",
	"requests": "requests",
	"yaml": "pyyaml",
	"prometheus_api_client": "prometheus-api-client",
	"autogen": "autogen",
	"langgraph": "langgraph"
}
missing = []
installed = []
for pkg, name in packages.items():
	try:
		importlib.import_module(pkg)
		installed.append(name)
	except ImportError:
		missing.append(name)
import sys
print(f"installed:{','.join(installed)}|missing:{','.join(missing)}")
`
	out, err := exec.Command(pyBin, "-c", pkgScript).CombinedOutput()
	if err != nil {
		fmt.Printf("⚠️  failed to run dependency check: %v\n", err)
		return false
	}

	outStr := strings.TrimSpace(string(out))
	if !strings.Contains(outStr, "|") {
		fmt.Printf("⚠️  unexpected check output: %q\n", outStr)
		return false
	}

	parts := strings.Split(outStr, "|")
	missingPart := strings.TrimPrefix(parts[1], "missing:")

	var missing []string
	if missingPart != "" {
		missing = strings.Split(missingPart, ",")
	}

	if len(missing) > 0 {
		fmt.Printf("⚠️  %s (Missing: %s)\n", versionStr, strings.Join(missing, ", "))
		return false
	}

	fmt.Printf("✅ %s (all dependencies installed)\n", versionStr)
	return true
}

// checkAPIKeys checks OpenAI API Key.
func checkAPIKeys() bool {
	fmt.Print("  LLM Credentials    ... ")
	openAIKey := os.Getenv("OPENAI_API_KEY")
	geminiKey := os.Getenv("GEMINI_API_KEY")

	if openAIKey == "" && geminiKey == "" {
		fmt.Println("⚠️  Neither OPENAI_API_KEY nor GEMINI_API_KEY is set (LLM brains will fail unless configured differently)")
		return false
	}

	var keys []string
	if openAIKey != "" {
		keys = append(keys, "OPENAI_API_KEY")
	}
	if geminiKey != "" {
		keys = append(keys, "GEMINI_API_KEY")
	}
	fmt.Printf("✅ configured (%s)\n", strings.Join(keys, ", "))
	return true
}

// checkStatus verifies connectivity to each tool binding backend.
func checkStatus(cmd *cobra.Command, args []string) error {
	fmt.Println("🔍 devops-agent — checking tool binding health")
	fmt.Println()

	allHealthy := true

	// Check Python Environment
	allHealthy = checkPythonEnvironment() && allHealthy

	// Check API Credentials
	allHealthy = checkAPIKeys() && allHealthy

	// Check Kubernetes
	allHealthy = checkKubernetes() && allHealthy

	// Check ArgoCD
	allHealthy = checkArgoCD() && allHealthy

	// Check Prometheus
	allHealthy = checkPrometheus() && allHealthy

	fmt.Println()
	if allHealthy {
		fmt.Println("✅ All systems and tool bindings are healthy")
	} else {
		fmt.Println("⚠️  Some dependencies or tool bindings are unreachable/missing — agents may have limited functionality")
	}

	return nil
}

// checkKubernetes verifies kubectl is available and can connect.
func checkKubernetes() bool {
	fmt.Print("  Kubernetes ... ")

	// Check if kubectl is available
	if _, err := exec.LookPath("kubectl"); err != nil {
		fmt.Println("❌ kubectl not found in PATH")
		return false
	}

	// Try cluster-info
	out, err := exec.Command("kubectl", "cluster-info", "--request-timeout=5s").CombinedOutput()
	if err != nil {
		if verbose {
			fmt.Printf("❌ unreachable\n    %s\n", string(out))
		} else {
			fmt.Println("❌ unreachable")
		}
		return false
	}

	fmt.Println("✅ connected")
	return true
}

// checkArgoCD verifies the ArgoCD server is reachable.
func checkArgoCD() bool {
	fmt.Print("  ArgoCD     ... ")

	// Try the ArgoCD CLI first
	if path, err := exec.LookPath("argocd"); err == nil {
		out, err := exec.Command(path, "version", "--client").CombinedOutput()
		if err == nil {
			if verbose {
				fmt.Printf("✅ CLI available\n    %s", string(out))
			} else {
				fmt.Println("✅ CLI available")
			}
			return true
		}
	}

	// Fall back to HTTP check on default ArgoCD port
	client := http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get("https://localhost:8080/api/v1/session")
	if err != nil {
		fmt.Println("⚠️  server not reachable (CLI not found, HTTP fallback failed)")
		return false
	}
	defer resp.Body.Close()

	fmt.Println("✅ server reachable")
	return true
}

// checkPrometheus verifies the Prometheus server is reachable.
func checkPrometheus() bool {
	fmt.Print("  Prometheus ... ")

	client := http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get("http://localhost:9090/-/healthy")
	if err != nil {
		fmt.Println("⚠️  not reachable at localhost:9090")
		return false
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		fmt.Println("✅ healthy")
		return true
	}

	fmt.Printf("⚠️  responded with status %d\n", resp.StatusCode)
	return false
}
