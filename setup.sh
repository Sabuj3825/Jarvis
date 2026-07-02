#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  JARVIS — Termux One-Shot Setup Script
#  Run this ONCE on a fresh Termux installation:
#
#       bash setup.sh
#
# ============================================================

RED='\033[91m'
GREEN='\033[92m'
YELLOW='\033[93m'
CYAN='\033[96m'
MAGENTA='\033[95m'
BOLD='\033[1m'
RESET='\033[0m'

echo -e "\n${MAGENTA}${BOLD}======================================================"
echo -e "  JARVIS — Termux Setup Script"
echo -e "======================================================${RESET}\n"

# ────────────────────────────────────────────────────────────
# STEP 1: Update Termux package index
# ────────────────────────────────────────────────────────────
echo -e "${CYAN}${BOLD}[1/5] Updating Termux package index...${RESET}"
pkg update -y && pkg upgrade -y
echo -e "${GREEN}✓ Package index updated${RESET}\n"

# ────────────────────────────────────────────────────────────
# STEP 2: Install system packages via pkg
# ────────────────────────────────────────────────────────────
echo -e "${CYAN}${BOLD}[2/5] Installing system packages (pkg)...${RESET}"

SYSTEM_PKGS=(
    "python"          # Python 3 interpreter
    "mpv"             # Media player (music + YouTube streaming)
    "termux-api"      # Battery, GPS, TTS, notifications
)

for pkg_name in "${SYSTEM_PKGS[@]}"; do
    echo -e "  ${YELLOW}→ Installing: $pkg_name${RESET}"
    pkg install -y "$pkg_name"
done

echo -e "${GREEN}✓ System packages installed${RESET}\n"

# ────────────────────────────────────────────────────────────
# STEP 3: Grant Termux storage permission (for music files)
# ────────────────────────────────────────────────────────────
echo -e "${CYAN}${BOLD}[3/5] Granting storage access permission...${RESET}"
termux-setup-storage
echo -e "${GREEN}✓ Storage permission requested (accept the popup)${RESET}\n"

# ────────────────────────────────────────────────────────────
# STEP 4: Install Python packages via pip
# ────────────────────────────────────────────────────────────
echo -e "${CYAN}${BOLD}[4/5] Installing Python packages (pip)...${RESET}"

python -m pip install --upgrade pip --break-system-packages 2>/dev/null || true

PYTHON_PKGS=(
    "colorama"        # Terminal color output
    "requests"        # HTTP / API calls
    "beautifulsoup4"  # Web scraper HTML parser
    "wikipedia"       # Wikipedia knowledge lookup
    "yt-dlp"          # YouTube stream URL resolver
)

for py_pkg in "${PYTHON_PKGS[@]}"; do
    echo -e "  ${YELLOW}→ Installing: $py_pkg${RESET}"
    pip install "$py_pkg"
done

echo -e "${GREEN}✓ Python packages installed${RESET}\n"

# ────────────────────────────────────────────────────────────
# STEP 5: Set Gemini API Key (optional)
# ────────────────────────────────────────────────────────────
echo -e "${CYAN}${BOLD}[5/5] Gemini API Key setup (optional)...${RESET}"
echo -e "  If you have a Gemini API key, paste it below."
echo -e "  Press ENTER to skip (cloud features will be disabled).\n"
read -p "  Gemini API Key: " api_key

if [ -n "$api_key" ]; then
    # Add to .bashrc so it persists across sessions
    echo "export GEMINI_API_KEY=\"$api_key\"" >> ~/.bashrc
    export GEMINI_API_KEY="$api_key"
    echo -e "${GREEN}✓ API key saved to ~/.bashrc${RESET}\n"
else
    echo -e "${YELLOW}⊘ Skipped. Jarvis will use local LLM only.${RESET}\n"
fi

# ────────────────────────────────────────────────────────────
# DONE — Run preflight check
# ────────────────────────────────────────────────────────────
echo -e "${MAGENTA}${BOLD}======================================================"
echo -e "  Setup complete! Running preflight check..."
echo -e "======================================================${RESET}\n"

python check_deps.py

echo -e "\n${MAGENTA}${BOLD}======================================================"
echo -e "  To start Jarvis, run:"
echo -e "  ${CYAN}python jarvis.py${RESET}"
echo -e "${MAGENTA}${BOLD}======================================================"
echo -e "\n  ${YELLOW}NOTE: For Ollama (local LLM), also run:${RESET}"
echo -e "  ${CYAN}pkg install ollama${RESET}"
echo -e "  ${CYAN}ollama pull qwen2.5:0.5b${RESET}"
echo -e "  ${CYAN}ollama serve &${RESET}   (run in background)\n"
