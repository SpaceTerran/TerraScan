"""Diff Parser - Parse unified diff format into structured data."""

import re
from dataclasses import dataclass, field


@dataclass
class DiffHunk:
    """Represents a single hunk in a diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str] = field(default_factory=list)


@dataclass
class DiffFile:
    """Represents a single file's diff."""

    path: str
    old_path: str | None = None
    is_new: bool = False
    is_deleted: bool = False
    is_binary: bool = False
    hunks: list[DiffHunk] = field(default_factory=list)
    content: str = ""

    def get_new_line_numbers(self) -> dict[int, str]:
        """Get a mapping of new file line numbers to their content."""
        line_map = {}
        for hunk in self.hunks:
            new_line = hunk.new_start
            for line in hunk.lines:
                if line.startswith("+") and not line.startswith("+++"):
                    line_map[new_line] = line[1:]
                    new_line += 1
                elif line.startswith("-") and not line.startswith("---"):
                    pass  # Deleted lines don't increment new line counter
                elif line.startswith(" ") or line == "":
                    line_map[new_line] = line[1:] if line.startswith(" ") else ""
                    new_line += 1
        return line_map


def parse_diff(diff_content: str) -> list[DiffFile]:
    """Parse a unified diff into a list of DiffFile objects."""
    files: list[DiffFile] = []
    current_file: DiffFile | None = None
    current_hunk: DiffHunk | None = None
    current_file_content: list[str] = []

    diff_header_pattern = re.compile(r"^diff --git a/(.*) b/(.*)$")
    old_file_pattern = re.compile(r"^--- (?:a/)?(.*)$")
    new_file_pattern = re.compile(r"^\+\+\+ (?:b/)?(.*)$")
    hunk_header_pattern = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    binary_pattern = re.compile(r"^Binary files .* differ$")

    lines = diff_content.split("\n")

    for line in lines:
        diff_match = diff_header_pattern.match(line)
        if diff_match:
            if current_file is not None:
                current_file.content = "\n".join(current_file_content)
                files.append(current_file)

            current_file = DiffFile(
                path=diff_match.group(2),
                old_path=diff_match.group(1),
            )
            current_file_content = [line]
            current_hunk = None
            continue

        if current_file is None:
            continue

        current_file_content.append(line)

        if binary_pattern.match(line):
            current_file.is_binary = True
            continue

        old_match = old_file_pattern.match(line)
        if old_match:
            if old_match.group(1) == "/dev/null":
                current_file.is_new = True
            continue

        new_match = new_file_pattern.match(line)
        if new_match:
            if new_match.group(1) == "/dev/null":
                current_file.is_deleted = True
            continue

        hunk_match = hunk_header_pattern.match(line)
        if hunk_match:
            current_hunk = DiffHunk(
                old_start=int(hunk_match.group(1)),
                old_count=int(hunk_match.group(2) or 1),
                new_start=int(hunk_match.group(3)),
                new_count=int(hunk_match.group(4) or 1),
            )
            current_file.hunks.append(current_hunk)
            continue

        if current_hunk is not None:
            current_hunk.lines.append(line)

    if current_file is not None:
        current_file.content = "\n".join(current_file_content)
        files.append(current_file)

    return files
