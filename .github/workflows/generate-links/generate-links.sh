#!/bin/bash
# Generate Markdown Links - Local Script
# Consolidates all steps from the GitHub Actions workflow into a single local script
# This script can be run from any Hugo website directory
#
# Usage:
#   cd /path/to/your/hugo/site
#   /path/to/reusable-workflows/.github/workflows/generate-links/generate-links.sh
#
# Or set as an alias:
#   alias generate-links='/path/to/reusable-workflows/.github/workflows/generate-links/generate-links.sh'

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/generate_links.py"

# Verify the Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo -e "${RED}❌ Error: generate_links.py not found at $PYTHON_SCRIPT${NC}"
    exit 1
fi

# Make script executable
chmod +x "$PYTHON_SCRIPT" 2>/dev/null || true

# Configuration - can be overridden via environment variables
CONTENT_FOLDER="${CONTENT_FOLDER:-content/blog}"
PROMPT_FILE="${PROMPT_FILE:-content/prompts/internal-link-optimize.md}"
CUSTOM_PROMPT="${CUSTOM_PROMPT:-}"
DEBUG="${DEBUG:-false}"
DRY_RUN="${DRY_RUN:-false}"

# Required: GitHub Copilot token
if [ -z "$COPILOT_GITHUB_TOKEN" ]; then
    echo -e "${RED}❌ Error: COPILOT_GITHUB_TOKEN environment variable is required${NC}"
    echo ""
    echo "Please set your GitHub Copilot token:"
    echo "  export COPILOT_GITHUB_TOKEN='your-token-here'"
    echo ""
    echo "To create a Personal Access Token:"
    echo "  1. Go to GitHub Settings > Developer settings > Personal access tokens > Tokens (classic)"
    echo "  2. Generate a new token (classic) with 'repo' scope"
    echo "  3. Export it as COPILOT_GITHUB_TOKEN"
    exit 1
fi

# Verify token is set
if [ "$DEBUG" = "true" ]; then
    TOKEN_LEN=${#COPILOT_GITHUB_TOKEN}
    if [ $TOKEN_LEN -gt 12 ]; then
        TOKEN_PREFIX="${COPILOT_GITHUB_TOKEN:0:8}"
        TOKEN_SUFFIX="${COPILOT_GITHUB_TOKEN: -8}"
        echo -e "${BLUE}Token verification: ${TOKEN_PREFIX}...${TOKEN_SUFFIX} (${TOKEN_LEN} chars)${NC}"
    fi
fi

# Determine Hugo directory (where the script is run from)
HUGO_DIR="$(pwd)"

# Check if we're in the right directory
if [ ! -f "$HUGO_DIR/config.toml" ] && [ ! -f "$HUGO_DIR/hugo.toml" ]; then
    echo -e "${YELLOW}⚠️  Warning: Not in Hugo directory (config.toml or hugo.toml not found)${NC}"
    echo "   Current directory: $HUGO_DIR"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${GREEN}✅ Using Python script: $PYTHON_SCRIPT${NC}"

# Check for required tools
echo -e "${BLUE}Checking prerequisites...${NC}"

# Check for Hugo
if ! command -v hugo &> /dev/null; then
    echo -e "${RED}❌ Error: Hugo is not installed or not in PATH${NC}"
    echo ""
    echo "Please install Hugo:"
    echo "  brew install hugo  # macOS"
    echo "  or visit https://gohugo.io/installation/"
    exit 1
fi
HUGO_VERSION=$(hugo version | head -n1)
echo -e "${GREEN}✅ Hugo found: $HUGO_VERSION${NC}"

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Error: Python 3 is not installed or not in PATH${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✅ Python found: $PYTHON_VERSION${NC}"

# Check for GitHub Copilot CLI
if ! command -v copilot &> /dev/null; then
    echo -e "${RED}❌ Error: GitHub Copilot CLI is not installed${NC}"
    echo ""
    echo "Please install GitHub Copilot CLI:"
    echo "  npm install -g @github/copilot"
    echo ""
    echo "Note: This requires Node.js v22+ and a GitHub Copilot subscription"
    exit 1
fi
echo -e "${GREEN}✅ Copilot CLI found: $(copilot --version 2>/dev/null || echo 'installed')${NC}"

# Test Copilot CLI authentication
echo -e "${BLUE}Testing Copilot CLI authentication...${NC}"
if copilot -p "test" --allow-all-tools --silent > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Copilot CLI authentication test passed${NC}"
else
    echo -e "${YELLOW}⚠️  Copilot CLI authentication test failed${NC}"
    echo "   This may still work if the token is valid. Continuing..."
fi

# Install Python dependencies
echo -e "${BLUE}Installing Python dependencies...${NC}"
python3 -m pip install --quiet --upgrade pip pyyaml requests 2>/dev/null || {
    echo -e "${YELLOW}⚠️  Warning: Could not install dependencies automatically${NC}"
    echo "   Please run: pip install pyyaml requests"
}

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Step 1: Read default prompt${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"

# Read prompt file
DEFAULT_PROMPT=""
PROMPT_FILE_PATH="$HUGO_DIR/$PROMPT_FILE"

if [ -n "$CUSTOM_PROMPT" ]; then
    echo -e "${BLUE}Using custom prompt from CUSTOM_PROMPT environment variable${NC}"
    DEFAULT_PROMPT="$CUSTOM_PROMPT"
elif [ -f "$PROMPT_FILE_PATH" ]; then
    echo -e "${BLUE}Reading prompt from: $PROMPT_FILE_PATH${NC}"
    DEFAULT_PROMPT=$(cat "$PROMPT_FILE_PATH")
    echo -e "${GREEN}✅ Successfully read prompt (${#DEFAULT_PROMPT} characters)${NC}"
else
    echo -e "${YELLOW}⚠️  Prompt file not found at $PROMPT_FILE_PATH${NC}"
    echo "   Available files in .cursor/:"
    ls -la "$HUGO_DIR/.cursor/" 2>/dev/null || echo "   .cursor/ directory does not exist"
    echo ""
    echo -e "${RED}❌ Error: No prompt provided${NC}"
    echo "   Please either:"
    echo "   1. Set CUSTOM_PROMPT environment variable, or"
    echo "   2. Ensure $PROMPT_FILE exists"
    exit 1
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Step 2: Get published blog posts list${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"

# Create temporary directory for Hugo list
TMP_DIR=$(mktemp -d)
HUGO_LIST_FILE="$TMP_DIR/hugo_list.csv"
trap "rm -rf $TMP_DIR" EXIT

echo -e "${BLUE}Running 'hugo list all' to get published posts...${NC}"
cd "$HUGO_DIR"

if hugo list all > "$HUGO_LIST_FILE" 2>/dev/null; then
    TOTAL_LINES=$(wc -l < "$HUGO_LIST_FILE" | tr -d ' ')
    if [ "$TOTAL_LINES" -le 1 ]; then
        echo -e "${RED}❌ Hugo list CSV contains no data rows (only header or empty)${NC}"
        echo "   This indicates no content was found or Hugo configuration issue"
        exit 1
    fi
    echo -e "${GREEN}✅ Generated hugo list (total lines: $TOTAL_LINES)${NC}"
    echo "   Python script will filter for published posts (draft=false) and limit to 10"
else
    echo -e "${RED}❌ Hugo list command failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Step 3: Generate markdown links${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"

# Set up environment variables for Python script
export COPILOT_GITHUB_TOKEN
export CONTENT_FOLDER
export CUSTOM_PROMPT
export DEFAULT_PROMPT
export HUGO_LIST_FILE="$HUGO_LIST_FILE"
export DEBUG
export DRY_RUN

if [ "$DEBUG" = "true" ]; then
    echo -e "${BLUE}Environment variables:${NC}"
    echo "  CONTENT_FOLDER: $CONTENT_FOLDER"
    echo "  PROMPT_FILE: $PROMPT_FILE"
    echo "  CUSTOM_PROMPT: ${CUSTOM_PROMPT:+set (${#CUSTOM_PROMPT} chars)}"
    echo "  DEFAULT_PROMPT: ${#DEFAULT_PROMPT} characters"
    echo "  HUGO_LIST_FILE: $HUGO_LIST_FILE"
    echo "  DEBUG: $DEBUG"
    echo "  DRY_RUN: $DRY_RUN"
    echo ""
fi

# Run the Python script
echo -e "${BLUE}Running Python script to generate links...${NC}"
python3 "$PYTHON_SCRIPT"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✅ Successfully generated markdown links${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
else
    echo ""
    echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}❌ Script failed with exit code $EXIT_CODE${NC}"
    echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
    exit $EXIT_CODE
fi
