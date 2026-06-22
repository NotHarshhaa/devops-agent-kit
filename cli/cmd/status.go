package cmd

import (
	"fmt"
	"net/http"
	"os/exec"
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

// checkStatus verifies connectivity to each tool binding backend.
func checkStatus(cmd *cobra.Command, args []string) error {
	fmt.Println("🔍 devops-agent — checking tool binding health")
	fmt.Println()

	allHealthy := true

	// Check Kubernetes
	allHealthy = checkKubernetes() && allHealthy

	// Check ArgoCD
	allHealthy = checkArgoCD() && allHealthy

	// Check Prometheus
	allHealthy = checkPrometheus() && allHealthy

	fmt.Println()
	if allHealthy {
		fmt.Println("✅ All tool bindings are reachable")
	} else {
		fmt.Println("⚠️  Some tool bindings are unreachable — agents may have limited functionality")
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
