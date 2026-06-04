#!/usr/bin/env python3
"""
Resolve README.md merge conflict in the migradiff repository.
Run from the repository root: python resolve_readme_conflict.py
"""

import os
import re
import subprocess
import sys

def main():
    # Check if README.md exists
    if not os.path.exists("README.md"):
        print("❌ ERROR: README.md not found. Are you in the migra repository?")
        sys.exit(1)

    print("🔧 Resolving README.md merge conflict...")

    # Read README.md
    with open("README.md", "r", encoding="utf-8") as f:
        content = f.read()

    # Check if conflict markers exist
    if "<<<<<<" not in content and "=======" not in content:
        print("⚠️  No conflict markers found. Already resolved?")
        sys.exit(0)

    print("📝 Found conflict markers. Resolving...")

    # Define the resolved Quickstart section
    resolved = """## Quickstart

### Install

```bash
pip install migradiff
```

Requires Python 3.10+ and a running PostgreSQL instance (12+).

To install from source:

```bash
git clone https://github.com/migradiff/migra
cd migra
pip install -e .
```

> **Note:** PyPI package is available on all releases.

### Basic Usage"""

    # Remove conflict markers and replace the section
    # Pattern: from ## Quickstart to ### Basic Usage (inclusive)
    pattern = r"## Quickstart.*?### Basic Usage"
    content = re.sub(pattern, resolved, content, flags=re.DOTALL)

    # Remove any remaining stray conflict markers
    content = re.sub(r"<<<<<<< HEAD\n", "", content)
    content = re.sub(r"=======\n", "", content)
    content = re.sub(r">>>>>>> origin/master\n", "", content)
    content = re.sub(r"<<<<<<.*?\n", "", content)
    content = re.sub(r">>>>>>> .*?\n", "", content)

    # Write back to README.md
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(content)

    print("✅ README.md conflict resolved")

    # Stage the file
    subprocess.run(["git", "add", "README.md"], check=True)
    print("✅ README.md staged")

    # Commit
    subprocess.run(
        ["git", "commit", "-m", "resolve: merge conflict in README.md"],
        check=True,
    )
    print("✅ Committed")

    # Push
    subprocess.run(["git", "push", "origin", "chore/setup-cicd"], check=True)
    print("✅ Pushed to origin")

    print("\n✨ Done! PR should now show 'No conflicts - ready to merge'")

if __name__ == "__main__":
    main()
