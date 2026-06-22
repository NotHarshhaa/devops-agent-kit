// devops-agent — AI-powered DevOps automation CLI.
//
// Entry point for the devops-agent binary. Delegates all command
// handling to the cmd package which uses Cobra for subcommand routing.
package main

import (
	"os"

	"github.com/NotHarshhaa/devops-agent-kit/cli/cmd"
)

func main() {
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
