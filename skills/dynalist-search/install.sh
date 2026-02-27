#!/usr/bin/env bash
# Install the dynalist-search skill for Claude Code

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_NAME="dynalist-search"
TARGET_DIR="${HOME}/.claude/skills/${SKILL_NAME}"

echo "Installing ${SKILL_NAME} skill..."

# Create target directory
mkdir -p "${TARGET_DIR}"

# Copy skill files
cp "${SCRIPT_DIR}/SKILL.md" "${TARGET_DIR}/"

echo "Skill installed to ${TARGET_DIR}"
echo "Claude Code will now use this skill for Dynalist searches."
