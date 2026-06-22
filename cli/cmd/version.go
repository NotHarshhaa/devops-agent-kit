package cmd

import (
	"fmt"
	"runtime"

	"github.com/spf13/cobra"
)

// Version information set at build time or defaulted here.
var (
	Version   = "0.1.0"
	GitCommit = "unknown"
	BuildDate = "unknown"
)

// versionCmd represents the "version" command.
var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Print CLI version",
	Long:  "Print the devops-agent CLI version, Go version, and build information.",
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Printf("devops-agent v%s\n", Version)
		fmt.Printf("  Git commit: %s\n", GitCommit)
		fmt.Printf("  Built:      %s\n", BuildDate)
		fmt.Printf("  Go version: %s\n", runtime.Version())
		fmt.Printf("  OS/Arch:    %s/%s\n", runtime.GOOS, runtime.GOARCH)
	},
}

func init() {
	rootCmd.AddCommand(versionCmd)
}
