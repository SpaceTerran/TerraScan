"""Chunker - Split large diffs into smaller chunks for API token limits."""

from diff_parser import DiffFile


def estimate_tokens(text: str) -> int:
    """Estimate token count (~4 chars per token for code)."""
    return len(text) // 4


def estimate_file_tokens(diff_file: DiffFile) -> int:
    """Estimate tokens for a single diff file."""
    return estimate_tokens(diff_file.content)


def chunk_diff_files(
    diff_files: list[DiffFile],
    max_tokens: int = 80000,
    min_files_per_chunk: int = 1,
) -> list[list[DiffFile]]:
    """Split diff files into chunks that fit within token limits."""
    if not diff_files:
        return []

    chunks: list[list[DiffFile]] = []
    current_chunk: list[DiffFile] = []
    current_tokens = 0

    # Reserve some tokens for system prompt and response
    effective_max = int(max_tokens * 0.7)

    for diff_file in diff_files:
        file_tokens = estimate_file_tokens(diff_file)

        # If single file exceeds limit, include it anyway
        if file_tokens > effective_max:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_tokens = 0
            chunks.append([diff_file])
            continue

        if current_tokens + file_tokens > effective_max and len(current_chunk) >= min_files_per_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

        current_chunk.append(diff_file)
        current_tokens += file_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
