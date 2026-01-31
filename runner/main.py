#!/usr/bin/env python3
"""AI Code Review - Entry point."""

import fnmatch
import os
import sys
from pathlib import Path

from config import load_config, Config
from ai_client import create_client
from gitea_client import GiteaClient
from diff_parser import parse_diff
from chunker import chunk_diff_files


def should_ignore(filepath: str, patterns: list) -> bool:
    """Check if file matches any ignore pattern."""
    for pattern in patterns:
        if fnmatch.fnmatch(filepath, pattern):
            return True
        if pattern.endswith("/") and filepath.startswith(pattern.rstrip("/")):
            return True
    return False


def load_prompt() -> str:
    """Load the system prompt."""
    prompt_file = Path("/app/config/prompts/system-prompt.txt")
    if prompt_file.exists():
        return prompt_file.read_text()
    return "You are a code reviewer. Review the changes and provide feedback."


def main() -> int:
    config = load_config()

    # Get environment variables (names are fixed)
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    gitea_token = os.environ.get("GITEA_TOKEN")
    repo_name = os.environ.get("REPO_NAME")       # From Gitea: gitea.repository
    pr_number = os.environ.get("PR_NUMBER")        # From Gitea: gitea.event.pull_request.number
    diff_path = os.environ.get("DIFF_PATH", "/dev/stdin")

    if not api_key and config.provider != "ollama":
        print("Error: OPENAI_API_KEY or ANTHROPIC_API_KEY required")
        return 1

    # Read diff
    if diff_path in ("/dev/stdin", "-"):
        diff_content = sys.stdin.read()
    else:
        diff_content = Path(diff_path).read_text()

    if not diff_content.strip():
        print("No changes to review")
        return 0

    # Parse and filter
    diff_files = parse_diff(diff_content)
    diff_files = [f for f in diff_files if not should_ignore(f.path, config.ignore_patterns)]

    if not diff_files:
        print("No files to review after filtering")
        return 0

    print(f"Reviewing {len(diff_files)} files")

    # Review with AI
    ai = create_client(config, api_key)
    prompt = load_prompt()
    chunks = chunk_diff_files(diff_files, max_tokens=config.max_tokens * 5)

    all_comments = []
    all_summaries = []

    for i, chunk in enumerate(chunks):
        print(f"Processing chunk {i+1}/{len(chunks)}")
        diff_text = "\n\n".join(f"### {f.path}\n```diff\n{f.content}\n```" for f in chunk)
        result = ai.review(prompt, f"Review these changes:\n\n{diff_text}")
        all_comments.extend(result.get("inline_comments", []))
        if result.get("summary"):
            all_summaries.append(result["summary"])

    # Limit comments by severity
    if len(all_comments) > config.max_comments:
        order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
        all_comments.sort(key=lambda c: order.get(c.get("severity", "info"), 3))
        all_comments = all_comments[:config.max_comments]

    # Post to Gitea
    if gitea_token and repo_name and pr_number:
        gitea = GiteaClient(config, gitea_token)
        gitea.post_review(repo_name, int(pr_number), all_comments, all_summaries)
    else:
        import json
        print(json.dumps({"comments": all_comments, "summaries": all_summaries}, indent=2))

    # Check fail threshold
    order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    fail_level = order.get(config.fail_on_severity, 0)
    for c in all_comments:
        if order.get(c.get("severity", "info"), 3) <= fail_level:
            print(f"Found {c['severity']} issue - failing")
            return 1

    print("Review completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
