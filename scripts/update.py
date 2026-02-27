#!/usr/bin/env python3
"""Update script for dynalist-archive: installs CLI tool and Claude Code skill."""

import subprocess
import sys
from pathlib import Path


def run_update() -> int:
    """Run the update workflow.

    Returns:
        int: Exit code (0 for success, non-zero for failure).
    """
    print("📦 Installing dynalist-archive tool...")
    result = subprocess.run(
        ["uv", "tool", "install", ".", "--reinstall", "--force"],
        capture_output=False,
    )
    if result.returncode != 0:
        print("❌ Failed to install tool")
        return 1

    print("🔧 Installing Claude Code skill...")
    skill_script = Path("skills/dynalist-search/install.sh")
    if skill_script.exists():
        skill_result = subprocess.run([str(skill_script)], capture_output=True, text=True)
        if skill_result.returncode != 0:
            print("❌ Skill installation failed:")
            if skill_result.stderr:
                print(f"   {skill_result.stderr.strip()}")
            print("   You can retry with: ./skills/dynalist-search/install.sh")
            return 1
    else:
        print("   Skill script not found, skipping")

    print("✅ Update complete!")
    return 0


if __name__ == "__main__":
    sys.exit(run_update())
