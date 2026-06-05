// pybox-launcher: a native trampoline that reads a config file adjacent to
// itself, sets up the environment, and exec's into nono.
//
// Because this is a real Mach-O/ELF binary (not a shell script), it can safely
// be the target of a #! shebang line, solving the double-shebang problem that
// arises when a shell script is used as a Python interpreter wrapper.
//
// Config file selection (based on argv[0] basename):
//   pip* invocations → pybox_pip_launcher.env
//   all others       → pybox_launcher.env
//
// Config file format (one KEY=VALUE per line, no quoting, # for comments):
//
//   PYBOX_NONO_PROFILE=/abs/path/to/profile.json
//   PYBOX_NOSANDBOX=/abs/path/to/python_nosandbox   (or pip_nosandbox)
//   PYBOX_MKDIR=/abs/path/to/dir1:/abs/path/to/dir2  (colon-separated, optional)
//   PYBOX_ENV_KEY=VALUE   (any PYBOX_ENV_* entry is set as KEY=VALUE in child env)
//
// The config file is located in the same directory as argv[0].
// When argv[0] is a symlink (as it will be for python, python3, pip, etc.), the
// symlink is NOT resolved — we use the directory of the symlink itself, because
// all pybox files live together in bin/.
package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

func fatalf(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "pybox-launcher: "+format+"\n", args...)
	os.Exit(1)
}

func main() {
	// Locate config file relative to the argv[0] symlink (not its resolved target).
	self := os.Args[0]
	if !filepath.IsAbs(self) {
		// When the shell invokes a binary by name (e.g. "python" with the venv
		// on PATH), execvp passes just the bare name as argv[0].  Joining with
		// cwd would produce the wrong directory (e.g. /tmp/python instead of
		// /venv/bin/python).  Search PATH instead to find the real location.
		if found, err := findExecutable(self); err == nil {
			self = found
		} else if cwd, err := os.Getwd(); err == nil {
			// Last resort: treat as relative to cwd (handles ./python style invocations).
			self = filepath.Join(cwd, self)
		}
	}
	binDir := filepath.Dir(self)

	// Select config file based on whether we were invoked as pip or python.
	configFilename := "pybox_launcher.env"
	if strings.HasPrefix(filepath.Base(self), "pip") {
		configFilename = "pybox_pip_launcher.env"
	}
	configPath := filepath.Join(binDir, configFilename)

	// Parse config file.
	f, err := os.Open(configPath)
	if err != nil {
		fatalf("cannot open config file %s: %v\nIs pybox installed correctly?", configPath, err)
	}
	defer f.Close()

	cfg := make(map[string]string)
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if !ok {
			fatalf("malformed config line: %q", line)
		}
		cfg[k] = v
	}
	if err := scanner.Err(); err != nil {
		fatalf("error reading config file: %v", err)
	}

	// Required fields.
	profile, ok := cfg["PYBOX_NONO_PROFILE"]
	if !ok {
		fatalf("PYBOX_NONO_PROFILE not set in %s", configPath)
	}
	nosandbox, ok := cfg["PYBOX_NOSANDBOX"]
	if !ok {
		fatalf("PYBOX_NOSANDBOX not set in %s", configPath)
	}

	// If we're already inside a nono sandbox (NONO_CAP_FILE is set), skip the
	// nono wrapper entirely and exec directly into the nosandbox binary.
	// The outer sandbox policy already constrains us; a nested nono run would
	// fail trying to write its audit log and read its profiles from paths the
	// outer sandbox blocks.
	if os.Getenv("NONO_CAP_FILE") != "" {
		if err := syscall.Exec(nosandbox, append([]string{nosandbox}, os.Args[1:]...), os.Environ()); err != nil {
			fatalf("exec %s: %v", nosandbox, err)
		}
	}

	// Check nono is on PATH.
	nonoPath, err := findExecutable("nono")
	if err != nil {
		fatalf("nono is required but not found on PATH.\n" +
			"pybox uses nono to enforce kernel-level sandbox policies.\n" +
			"Install it from https://nono.sh")
	}

	// mkdir -p any required directories.
	if dirs, ok := cfg["PYBOX_MKDIR"]; ok {
		for _, dir := range strings.Split(dirs, ":") {
			dir = strings.TrimSpace(dir)
			if dir == "" {
				continue
			}
			if err := os.MkdirAll(dir, 0o755); err != nil {
				fatalf("mkdir %s: %v", dir, err)
			}
		}
	}

	// Build the environment for the child process.
	// Start with the current environment, then apply PYBOX_ENV_* overrides.
	env := os.Environ()
	for k, v := range cfg {
		if strings.HasPrefix(k, "PYBOX_ENV_") {
			varName := strings.TrimPrefix(k, "PYBOX_ENV_")
			env = setenv(env, varName, v)
		}
	}

	// Build argv for: nono run [--silent] --allow-cwd --profile <profile> -- <nosandbox> [original args...]
	// --silent is the default; omitted when PYBOX_INTERACTIVE=1 so the user
	// can see the capabilities summary (useful for debugging sandbox policies).
	argv := []string{nonoPath, "run"}
	if os.Getenv("PYBOX_INTERACTIVE") != "1" {
		argv = append(argv, "--silent")
	}
	argv = append(argv, "--allow-cwd", "--profile", profile, "--", nosandbox)
	argv = append(argv, os.Args[1:]...)

	// exec — replaces this process entirely.
	if err := syscall.Exec(nonoPath, argv, env); err != nil {
		fatalf("exec %s: %v", nonoPath, err)
	}
}

// setenv sets or replaces a KEY=VALUE entry in an environ slice.
func setenv(env []string, key, value string) []string {
	prefix := key + "="
	for i, e := range env {
		if strings.HasPrefix(e, prefix) {
			env[i] = prefix + value
			return env
		}
	}
	return append(env, prefix+value)
}

// findExecutable searches PATH for the named executable, mirroring exec.LookPath
// but without importing os/exec to keep the binary small.
func findExecutable(name string) (string, error) {
	pathEnv := os.Getenv("PATH")
	for _, dir := range filepath.SplitList(pathEnv) {
		candidate := filepath.Join(dir, name)
		info, err := os.Stat(candidate)
		if err == nil && !info.IsDir() && info.Mode()&0o111 != 0 {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("%q not found in PATH", name)
}
