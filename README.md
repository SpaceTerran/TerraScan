# TerraScan

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Build Status](https://github.com/SpaceTerran/TerraScan/actions/workflows/build-image.yml/badge.svg?branch=main)](https://github.com/SpaceTerran/TerraScan/actions/workflows/build-image.yml)

Self-hosted AI code review bot for Gitea. Automatically reviews pull requests and posts inline comments.

## Features

- Automatic PR reviews triggered by Gitea Actions
- Inline comments on specific lines plus summary comments
- Supports OpenAI and Anthropic (Claude)
- Configurable severity thresholds for blocking PRs
- Stateless Docker container — all config via environment variables
- Cleans up previous review comments on re-runs

## Hosting Options

This project supports both **GitHub** and **Gitea** hosting:

### Using with Gitea (Recommended for Self-Hosting)

Fork this repository to your Gitea instance and update the configuration:

1. **Update these files with your values:**
   - `.gitea/workflows/build-image.yml`: Set `REGISTRY` and `IMAGE_NAME`
   - `config/review-config.yml`: Set `gitea_url`
   - `docker/Dockerfile`: Update `org.opencontainers.image.source` label

2. **Add secrets** at your org level (`/org/YOUR-ORG/settings/actions/secrets`):
   - `OPENAI_API_CODEREVIEW_KEY` — OpenAI API key
   - `GTOKEN` — Gitea token with package:write and repo:write access

3. **Push to trigger the build** — the container will be built and pushed to your registry

4. **Delete `.github/` folder** (optional) — it's only used for GitHub hosting and won't run on Gitea

### Using with GitHub (Pre-built Container)

The pre-built container is available on GitHub Container Registry:

```bash
docker pull ghcr.io/spaceterran/terrascan:latest
```

## Quick Start

1. **Set organization secrets** in Gitea (`/org/YOUR-ORG/settings/actions/secrets`):
   - `OPENAI_API_CODEREVIEW_KEY` — OpenAI API key
   - `GTOKEN` — Gitea token with repo write access

2. **Add to your workflow** (`.gitea/workflows/CICD.yml`):

```yaml
  AIReview:
    name: AI Code Review
    if: gitea.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: https://gitea.com/actions/checkout@v6
        with:
          fetch-depth: 0

      - name: Run AI Code Review
        run: |
          BASE_REF="${{ gitea.event.pull_request.base.ref }}"
          git fetch origin "$BASE_REF"
          DIFF_CONTENT=$(git diff "origin/$BASE_REF"...HEAD 2>/dev/null) || \
            DIFF_CONTENT=$(git diff "origin/$BASE_REF"..HEAD 2>/dev/null) || exit 0
          [ -z "$DIFF_CONTENT" ] && exit 0

          # CHANGE THESE: Replace with your Gitea instance and org
          echo "${{ secrets.GTOKEN }}" | docker login your-gitea-instance.com -u ${{ gitea.actor }} --password-stdin
          docker pull your-gitea-instance.com/your-org/terrascan:latest

          echo "$DIFF_CONTENT" | docker run --rm -i \
            -e OPENAI_API_KEY=${{ secrets.OPENAI_API_CODEREVIEW_KEY }} \
            -e GITEA_TOKEN=${{ secrets.GTOKEN }} \
            -e REPO_NAME=${{ gitea.repository }} \
            -e PR_NUMBER=${{ gitea.event.pull_request.number }} \
            your-gitea-instance.com/your-org/terrascan:latest
```

3. **Open a PR** — the bot will post review comments automatically.

## Configuration Reference

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes* | OpenAI API key |
| `ANTHROPIC_API_KEY` | Yes* | Anthropic API key (alternative to OpenAI) — use only one, not both |
| `GITEA_TOKEN` | Yes | Token with repo write access |
| `REPO_NAME` | Yes | Repository path (e.g., `org/repo`) |
| `PR_NUMBER` | Yes | Pull request number |
| `DIFF_PATH` | No | Path to diff file (default: `/dev/stdin`) |

*One AI provider key required (OpenAI or Anthropic; use only one).

### Config File Options

Edit `config/review-config.yml` to customize behavior:

| Setting | Default | Description |
|---------|---------|-------------|
| `provider` | `openai` | AI provider: `openai` or `anthropic` |
| `model` | `gpt-5.2-codex` | Model name for the selected provider |
| `fail_on_severity` | `critical` | Minimum severity to fail CI: `critical`, `error`, `warning`, `none` |
| `max_comments` | `50` | Maximum inline comments per PR |
| `max_tokens` | `16000` | Maximum AI response length |
| `temperature` | `0.2` | AI creativity (0.0 = deterministic) |

## Architecture

```
PR Created
    |
    v
Gitea Actions workflow
    |
    v
git diff origin/main...HEAD
    |
    v
+---------------------------+
|  TerraScan Container      |
|  +---------------------+  |
|  | main.py             |  |
|  | diff_parser.py      |  |
|  | ai_client.py        |  |
|  | gitea_client.py     |  |
|  +---------------------+  |
+---------------------------+
    |
    v
AI API (OpenAI or Anthropic)
    |
    v
Gitea API (post comments)
```

## Project Structure

```
terrascan/
├── .gitea/workflows/
│   └── build-image.yml       # Gitea Actions (for forkers)
├── .github/workflows/
│   └── build-image.yml       # GitHub Actions (GHCR publishing)
├── config/
│   ├── review-config.yml     # Main configuration
│   └── prompts/
│       └── system-prompt.txt # AI instructions
├── runner/
│   ├── main.py               # Entry point
│   ├── config.py             # Config loader
│   ├── ai_client.py          # AI provider clients
│   ├── gitea_client.py       # Gitea API integration
│   ├── diff_parser.py        # Git diff parser
│   ├── chunker.py            # Large diff handling
│   └── requirements.txt      # Python dependencies
├── docker/
│   └── Dockerfile            # Container build
└── examples/
    └── ai-review-job.yml     # Example workflow snippet
```

<details>
<summary><strong>Supported File Types</strong></summary>

### Reviewed by Default

**Code:** `.py`, `.js`, `.ts`, `.sh`, `.sql`, `.html`

**Infrastructure:** `.yml`, `.yaml`, `.j2`, `.tf`, `.tfvars`, `.hcl`, `Dockerfile`

**Configuration:** `.json`, `.toml`, `.xml`, `.cfg`, `.conf`, `.ini`, `.env`, `hosts`

**Documentation:** `.md`, `.txt`, `.gitignore`

### Ignored by Default

- Lock files (`*.lock`, `package-lock.json`, `yarn.lock`, `poetry.lock`)
- Minified assets (`*.min.js`, `*.min.css`)
- Dependencies (`node_modules/`, `vendor/`)
- Build output (`dist/`, `build/`, `*.pyc`, `*.so`, `*.exe`)
- Binary files (`*.png`, `*.jpg`, `*.gif`, `*.woff`, `*.woff2`)
- Terraform state and cache (`*.tfstate`, `*.tfstate.backup`, `.terraform/`)
- OS files (`.DS_Store`, `Thumbs.db`)

</details>

## Requirements

- Gitea 1.25.4 (tested); 1.19+ with Actions enabled recommended
- Gitea runner with Docker access
- One of: OpenAI API key or Anthropic API key (use only one)

## Forking to Gitea

When forking this repository to your Gitea instance:

1. **Update `.gitea/workflows/build-image.yml`:**
   ```yaml
   env:
     REGISTRY: your-gitea-instance.com        # Your Gitea domain
     IMAGE_NAME: your-org/terrascan           # Your org/package name
   ```

2. **Update `config/review-config.yml`:**
   ```yaml
   gitea_url: https://your-gitea-instance.com
   ```

3. **Update `docker/Dockerfile`:**
   ```dockerfile
   LABEL org.opencontainers.image.source="https://your-gitea-instance.com/your-org/TerraScan"
   ```

4. **Add secrets to your Gitea org:**
   - `GTOKEN` — Personal access token with `package:write` and `repo:write` scope

5. **Optional:** Delete the `.github/` folder (GitHub Actions won't run on Gitea anyway)

## Contributing

Contributions are welcome! Here's how to get involved:

1. **Report bugs or request features** — Open an [issue](https://github.com/SpaceTerran/TerraScan/issues)
2. **Submit code changes:**
   - Fork the repository
   - Create a feature branch (`git checkout -b feature/my-improvement`)
   - Make your changes and commit
   - Push to your fork and open a pull request

Pull requests are reviewed and merged by the maintainers. Please ensure your changes:
- Don't break existing Gitea Actions compatibility
- Include clear commit messages
- Update documentation if adding new features

## Troubleshooting

**No comments appearing:**
- Verify `GITEA_TOKEN` has repo write access
- Check the AI API key is valid
- Review the job logs for errors

**"0 files to review":**
- All files match ignore patterns in `config/review-config.yml`

**Review quality issues:**
- Edit prompts in `config/prompts/system-prompt.txt`
