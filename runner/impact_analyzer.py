"""Impact Analyzer - Analyze potential impacts of code changes."""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ChangeImpact:
    """Impact analysis for a single changed file."""

    file_path: str
    change_summary: str  # What changed (AI-generated summary)
    code_context: str = ""  # The key line(s) of code that changed
    affected_areas: list[str] = field(default_factory=list)  # What functionality is affected
    potential_impacts: list[str] = field(default_factory=list)  # How this might affect the project
    review_focus: list[str] = field(default_factory=list)  # What the reviewer should check
    related_files: list[str] = field(default_factory=list)  # Files that reference or are referenced


@dataclass
class ImpactContext:
    """Full impact analysis for the PR."""

    impacts: list[ChangeImpact] = field(default_factory=list)
    project_overview: str = ""  # Brief project structure
    critical_files: list[str] = field(default_factory=list)  # Files needing careful review
    context_files: list[tuple[str, str]] = field(default_factory=list)  # (path, content) tuples
    token_estimate: int = 0


# Prompt for AI impact analysis
IMPACT_ANALYSIS_PROMPT = """Analyze the potential impact of this change on the project.

**File:** {file_path}
**Change type:** {change_type}

**The specific changes:**
```diff
{diff_content}
```

**Files that reference this file:**
{referencing_files}

Analyze and return JSON (no markdown code fences):
{{
    "change_summary": "Brief description of what changed",
    "code_context": "The 1-3 key lines of code that were added/modified (from the diff, without +/- prefixes)",
    "affected_areas": ["List of functionality/features affected"],
    "potential_impacts": [
        "Impact 1: How this might affect other parts",
        "Impact 2: What could break or behave differently"
    ],
    "review_focus": [
        "Specific thing reviewer should verify",
        "Another thing to check"
    ],
    "critical_files": ["files/that/need/review.py"]
}}

For code_context: Extract the most important 1-3 lines that show the actual change. For example:
- For a Dockerfile: "RUN apk add --no-cache dumb-init tini"
- For a JS file: "logError('header not found');"
- For CSS: "color: var(--undefined-color);"

Be specific and actionable. Focus on:
- Breaking changes and compatibility
- Security implications
- Side effects on dependent code
- Configuration or environment changes needed"""


def estimate_tokens(text: str) -> int:
    """Estimate token count (rough approximation: ~4 chars per token)."""
    return len(text) // 4


def find_references(file_path: str, repo_root: str) -> list[str]:
    """
    Find files that reference the given file.
    Uses multiple strategies based on file type.
    """
    references = set()
    path = Path(file_path)
    filename = path.name
    stem = path.stem

    def grep_for_pattern(pattern: str) -> set[str]:
        """Run grep and return matching file paths."""
        try:
            result = subprocess.run(
                ["grep", "-rl", "--include=*", pattern, repo_root],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return {
                    line.strip()
                    for line in result.stdout.strip().split("\n")
                    if line.strip() and not line.strip().endswith(".git")
                }
        except (subprocess.TimeoutExpired, Exception):
            pass
        return set()

    # Strategy 1: Grep for filename/path
    references.update(grep_for_pattern(f'"{filename}"'))
    references.update(grep_for_pattern(f"'{filename}'"))
    references.update(grep_for_pattern(file_path))

    # Strategy 2: For code files, search for import patterns
    if file_path.endswith(".py"):
        # Python imports: "from module import" or "import module"
        references.update(grep_for_pattern(f"import {stem}"))
        references.update(grep_for_pattern(f"from {stem}"))

    # Strategy 3: For config files, search in common include patterns
    if file_path.endswith((".yml", ".yaml")):
        references.update(grep_for_pattern(f"include.*{filename}"))
        references.update(grep_for_pattern(f"import.*{filename}"))

    # Strategy 4: For Terraform files
    if file_path.endswith(".tf"):
        references.update(grep_for_pattern(f"module.*{stem}"))
        references.update(grep_for_pattern(f"source.*{stem}"))

    # Strategy 5: For Docker files
    if filename == "Dockerfile" or file_path.endswith("docker-compose.yml"):
        references.update(grep_for_pattern("docker"))
        references.update(grep_for_pattern("container"))

    # Exclude self and normalize paths
    normalized = set()
    for ref in references:
        rel_path = os.path.relpath(ref, repo_root) if os.path.isabs(ref) else ref
        if rel_path != file_path and not rel_path.startswith(".git"):
            normalized.add(rel_path)

    return list(normalized)[:20]  # Limit to avoid overwhelming


def get_change_type(diff_file) -> str:
    """Determine the type of change from a DiffFile object."""
    if diff_file.is_new:
        return "added"
    elif diff_file.is_deleted:
        return "deleted"
    elif diff_file.old_path and diff_file.old_path != diff_file.path:
        return "renamed"
    else:
        return "modified"


def analyze_single_change(ai_client, diff_file, references: list[str], repo_root: str) -> ChangeImpact:
    """
    Analyze the impact of a single file change using AI.

    Args:
        ai_client: AI client with quick_query method
        diff_file: DiffFile object with the change
        references: List of files that reference this file
        repo_root: Root directory of the repository

    Returns:
        ChangeImpact with analysis results
    """
    change_type = get_change_type(diff_file)

    # Format referencing files
    if references:
        ref_text = "\n".join(f"- {ref}" for ref in references[:10])
    else:
        ref_text = "(No direct references found)"

    # Build the prompt
    prompt = IMPACT_ANALYSIS_PROMPT.format(
        file_path=diff_file.path,
        change_type=change_type,
        diff_content=diff_file.content[:3000],  # Limit diff size
        referencing_files=ref_text,
    )

    try:
        response = ai_client.quick_query(prompt)

        # Try to parse JSON response
        # Handle markdown code fences if present
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1].split("```")[0]

        data = json.loads(response.strip())

        return ChangeImpact(
            file_path=diff_file.path,
            change_summary=data.get("change_summary", ""),
            code_context=data.get("code_context", ""),
            affected_areas=data.get("affected_areas", []),
            potential_impacts=data.get("potential_impacts", []),
            review_focus=data.get("review_focus", []),
            related_files=references + data.get("critical_files", []),
        )
    except (json.JSONDecodeError, Exception) as e:
        # Fallback to basic impact
        print(f"Warning: Could not parse impact analysis for {diff_file.path}: {e}")
        return ChangeImpact(
            file_path=diff_file.path,
            change_summary=f"File {change_type}",
            affected_areas=[],
            potential_impacts=[],
            review_focus=[],
            related_files=references,
        )


def load_file_preview(file_path: str, repo_root: str, max_lines: int = 60) -> str:
    """Load a preview of a file (first N lines)."""
    full_path = Path(repo_root) / file_path
    try:
        if full_path.exists():
            with open(full_path) as f:
                lines = f.readlines()[:max_lines]
                return "".join(lines)
    except Exception:
        pass
    return ""


def select_context(
    impacts: list[ChangeImpact], repo_root: str, token_budget: int
) -> list[tuple[str, str]]:
    """
    Select most relevant context files within token budget.
    Prioritizes files marked as critical by impact analysis.

    Returns:
        List of (path, content) tuples
    """
    context_files = []
    used_tokens = 0

    # Collect all critical files from impact analysis
    critical = set()
    for impact in impacts:
        for f in impact.related_files:
            # Only include files that exist and aren't already being changed
            changed_paths = {i.file_path for i in impacts}
            if f not in changed_paths:
                critical.add(f)

    # Priority order: sort by how many impacts reference them
    file_counts = {}
    for impact in impacts:
        for f in impact.related_files:
            file_counts[f] = file_counts.get(f, 0) + 1

    sorted_files = sorted(critical, key=lambda f: file_counts.get(f, 0), reverse=True)

    for path in sorted_files:
        content = load_file_preview(path, repo_root)
        if not content:
            continue

        tokens = estimate_tokens(content)
        if used_tokens + tokens <= token_budget:
            context_files.append((path, content))
            used_tokens += tokens

        if len(context_files) >= 10:  # Limit number of context files
            break

    return context_files


def generate_project_overview(repo_root: str) -> str:
    """Generate a brief project structure overview."""
    overview_parts = []

    # Try to read common structure indicators
    common_dirs = [
        "src",
        "app",
        "lib",
        "runner",
        "config",
        "ansible",
        "terraform",
        "docker",
        "roles",
        "playbooks",
        "modules",
        ".gitea",
        ".github",
        "tests",
        "scripts",
    ]

    existing_dirs = []
    for d in common_dirs:
        if (Path(repo_root) / d).exists():
            existing_dirs.append(d)

    if existing_dirs:
        overview_parts.append("Project structure:")
        for d in existing_dirs:
            overview_parts.append(f"  {d}/")

    # Check for common project files
    common_files = [
        "Dockerfile",
        "docker-compose.yml",
        "requirements.txt",
        "package.json",
        "main.tf",
        "site.yml",
        "playbook.yml",
    ]

    existing_files = []
    for f in common_files:
        if (Path(repo_root) / f).exists():
            existing_files.append(f)

    if existing_files:
        overview_parts.append("Key files: " + ", ".join(existing_files))

    return "\n".join(overview_parts) if overview_parts else "Standard project structure"


def analyze_impacts(
    diff_files: list, repo_root: str, ai_client, config
) -> ImpactContext:
    """
    Analyze potential impacts of all changes.

    Args:
        diff_files: List of DiffFile objects from diff_parser
        repo_root: Root directory of the repository
        ai_client: AI client with quick_query method
        config: Config object with impact settings

    Returns:
        ImpactContext with full analysis
    """
    impacts = []
    all_critical_files = set()

    # Limit the number of files to analyze
    max_files = getattr(config, "impact_max_files", 10)
    files_to_analyze = diff_files[:max_files]

    for diff in files_to_analyze:
        # Skip binary files
        if diff.is_binary:
            continue

        # Phase 1: Structural - what references this file?
        if getattr(config, "impact_include_references", True):
            references = find_references(diff.path, repo_root)
        else:
            references = []

        # Phase 2: Semantic - what's the impact of these specific changes?
        impact = analyze_single_change(ai_client, diff, references, repo_root)
        impacts.append(impact)

        # Collect critical files
        all_critical_files.update(impact.related_files)

    # Generate project overview
    project_overview = generate_project_overview(repo_root)

    # Select context within token budget
    token_budget = getattr(config, "impact_token_budget", 6000)
    context_files = select_context(impacts, repo_root, token_budget)

    # Calculate total token estimate
    token_estimate = sum(estimate_tokens(content) for _, content in context_files)
    for impact in impacts:
        token_estimate += estimate_tokens(str(impact))

    return ImpactContext(
        impacts=impacts,
        project_overview=project_overview,
        critical_files=list(all_critical_files)[:20],
        context_files=context_files,
        token_estimate=token_estimate,
    )


def format_impact_message(diff_text: str, impact_context: ImpactContext) -> str:
    """
    Format the user message with impact analysis for the AI review.

    Args:
        diff_text: Original diff text
        impact_context: ImpactContext with analysis

    Returns:
        Formatted message including impact analysis
    """
    parts = []

    # Project overview
    if impact_context.project_overview:
        parts.append("## Project Overview\n```")
        parts.append(impact_context.project_overview)
        parts.append("```\n")

    # Impact analysis for each changed file
    parts.append("## Changes and Their Impacts\n")

    for i, impact in enumerate(impact_context.impacts, 1):
        parts.append(f"### {i}. {impact.file_path} ({get_change_type_label(impact)})\n")

        if impact.change_summary:
            parts.append(f"**Summary:** {impact.change_summary}\n")

        if impact.affected_areas:
            parts.append(f"**Affected areas:** {', '.join(impact.affected_areas)}\n")

        if impact.potential_impacts:
            parts.append("**Potential impacts:**")
            for pi in impact.potential_impacts:
                parts.append(f"- {pi}")
            parts.append("")

        if impact.review_focus:
            parts.append("**Review focus:**")
            for rf in impact.review_focus:
                parts.append(f"- {rf}")
            parts.append("")

        if impact.related_files:
            parts.append(f"**Files to verify:** {', '.join(impact.related_files[:5])}\n")

        parts.append("---\n")

    # Context files
    if impact_context.context_files:
        parts.append("## Related Context Files\n")
        for path, content in impact_context.context_files:
            parts.append(f"### {path}")
            parts.append("```")
            parts.append(content[:2000])  # Limit content size
            if len(content) > 2000:
                parts.append("... (truncated)")
            parts.append("```\n")

    # The actual diff
    parts.append("## Full Diff\n")
    parts.append(diff_text)

    # Review instructions
    parts.append("\n## Review Instructions")
    parts.append("1. For each change, verify the identified potential impacts")
    parts.append("2. Check the 'Files to verify' actually handle the changes correctly")
    parts.append("3. Look for impacts the analysis may have missed")
    parts.append("4. Focus on the changed lines (+ and -) in the diff")

    return "\n".join(parts)


def get_change_type_label(impact: ChangeImpact) -> str:
    """Get a human-readable label for the change type."""
    # This is a simplified version - actual change type from DiffFile not stored in ChangeImpact
    if "added" in impact.change_summary.lower():
        return "ADDED"
    elif "deleted" in impact.change_summary.lower() or "removed" in impact.change_summary.lower():
        return "DELETED"
    elif "renamed" in impact.change_summary.lower():
        return "RENAMED"
    return "MODIFIED"
