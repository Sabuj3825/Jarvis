"""
========================================================
JARVIS DEPENDENCY GUARDIAN
========================================================
Runs BEFORE any third-party imports in jarvis.py.
Uses ONLY Python stdlib (os, sys, shutil, subprocess)
so it can never itself crash from a missing package.

If critical packages are missing → shows exactly what
to run, then exits cleanly. No ugly tracebacks.
========================================================
"""

import os
import sys
import shutil
import subprocess

# --------------------------------------------------------
# Color codes using raw ANSI (no colorama needed here)
# --------------------------------------------------------
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
MAGENTA= "\033[95m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def _print_header():
    print(f"\n{MAGENTA}{BOLD}{'='*54}{RESET}")
    print(f"{MAGENTA}{BOLD}  JARVIS — Dependency Guardian{RESET}")
    print(f"{MAGENTA}{BOLD}{'='*54}{RESET}")

def _check_python_package(package_name, import_name=None):
    """Try importing a package. Returns True if available."""
    if import_name is None:
        import_name = package_name
    try:
        __import__(import_name)
        return True
    except ImportError:
        return False

def _check_binary(binary_name):
    """Check if a system binary exists in PATH."""
    return shutil.which(binary_name) is not None

def run_dependency_check():
    """
    Full dependency audit. Exits with instructions if
    any CRITICAL package is missing.
    """

    # ====================================================
    # 1. CRITICAL Python packages (program cannot run without these)
    # ====================================================
    CRITICAL = [
        # (import_name, pip_package_name, description)
        ("colorama",         "colorama",         "Terminal color output"),
        ("requests",         "requests",         "HTTP requests (web search, Gemini API)"),
        ("bs4",              "beautifulsoup4",    "Web scraper HTML parser"),
        ("wikipedia",        "wikipedia",         "Wikipedia knowledge lookup"),
    ]

    # ====================================================
    # 2. OPTIONAL system binaries (features degrade gracefully)
    # ====================================================
    OPTIONAL_BINS = [
        # (binary,              pkg_install_cmd,            feature_affected)
        ("mpv",                 "pkg install mpv",           "Local music & YouTube streaming"),
        ("yt-dlp",              "pip install yt-dlp",        "YouTube audio/video streaming"),
        ("termux-tts-speak",    "pkg install termux-api",    "Text-to-speech voice output"),
        ("termux-battery-status","pkg install termux-api",   "Battery status command"),
        ("termux-location",     "pkg install termux-api",    "GPS location command"),
    ]

    missing_critical = []
    missing_optional = []

    # --- Check critical packages ---
    for import_name, pip_name, description in CRITICAL:
        if not _check_python_package(import_name):
            missing_critical.append((pip_name, description))

    # --- Check optional binaries ---
    for binary, install_cmd, feature in OPTIONAL_BINS:
        if not _check_binary(binary):
            missing_optional.append((binary, install_cmd, feature))

    # ====================================================
    # 3. REPORT
    # ====================================================
    all_ok = len(missing_critical) == 0

    if missing_critical or missing_optional:
        _print_header()

    if missing_critical:
        print(f"\n{RED}{BOLD}[CRITICAL] Missing Python packages — Jarvis CANNOT start:{RESET}")
        print(f"{RED}{'─'*54}{RESET}")
        for pkg, desc in missing_critical:
            print(f"  {RED}✗{RESET}  {BOLD}{pkg:<20}{RESET}  ({desc})")

        print(f"\n{YELLOW}{BOLD}Fix: Run this command in Termux:{RESET}")
        pkgs = " ".join(p for p, _ in missing_critical)
        print(f"\n  {CYAN}pip install {pkgs}{RESET}\n")
        print(f"{RED}{'─'*54}{RESET}")
        print(f"{RED}Aborting. Re-run jarvis.py after installing.{RESET}\n")
        sys.exit(1)

    if missing_optional:
        print(f"\n{YELLOW}{BOLD}[WARNING] Optional components not found (features will be limited):{RESET}")
        print(f"{YELLOW}{'─'*54}{RESET}")
        for binary, install_cmd, feature in missing_optional:
            print(f"  {YELLOW}⚠{RESET}  {BOLD}{binary:<25}{RESET}  → {feature}")
            print(f"     Install: {CYAN}{install_cmd}{RESET}")
        print(f"{YELLOW}{'─'*54}{RESET}")
        print(f"{YELLOW}Jarvis will start but the above features will not work.{RESET}\n")

    # ====================================================
    # 4. Also validate Ollama (local LLM) — warn only
    # ====================================================
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:11434", timeout=2)
    except Exception:
        if not missing_optional:  # only print header if not already shown
            pass  # don't print header again
        print(f"\n{YELLOW}{BOLD}[WARNING] Ollama is not running on port 11434.{RESET}")
        print(f"  The local LLM routing will fall back to web-only mode.")
        print(f"  Start Ollama with: {CYAN}ollama serve{RESET}")
        print(f"  Pull model with:   {CYAN}ollama pull qwen2.5:0.5b{RESET}\n")

    return all_ok


# Auto-run when imported
if __name__ != "__main__":
    run_dependency_check()

# Can also be run standalone: python check_deps.py
if __name__ == "__main__":
    ok = run_dependency_check()
    if ok:
        print(f"\n{GREEN}{BOLD}[OK] All critical dependencies satisfied.{RESET}")
        print(f"{GREEN}     You can now run: python jarvis.py{RESET}\n")
