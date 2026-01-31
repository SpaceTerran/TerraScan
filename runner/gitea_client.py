"""Gitea API client for posting review comments."""

import requests
from config import Config


class GiteaClient:
    """Client for posting review comments to Gitea PRs."""

    def __init__(self, config: Config, token: str):
        self.config = config
        self.token = token
        self.headers = {
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
        }

    def _get_pr_head_sha(self, repo_name: str, pr_number: int) -> str:
        """Get the head commit SHA for a PR."""
        url = f"{self.config.gitea_url}/api/v1/repos/{repo_name}/pulls/{pr_number}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json().get("head", {}).get("sha", "")

    def post_review(
        self,
        repo_name: str,
        pr_number: int,
        comments: list,
        summaries: list,
        impact_context=None
    ) -> None:
        """Post inline comments and summary to a PR."""
        head_sha = self._get_pr_head_sha(repo_name, pr_number)
        if not head_sha:
            print("Warning: Could not get head SHA, skipping inline comments")
            return

        icons = self.config.severity_icons or {
            "critical": "🔴", "error": "🟠", "warning": "🟡", "info": "🔵"
        }

        # Post inline comments as a review
        if comments:
            formatted = []
            severity_counts = {"critical": 0, "error": 0, "warning": 0, "info": 0}

            for c in comments:
                sev = c.get("severity", "info")
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
                icon = icons.get(sev, "💬")

                # Build comment body with optional code snippet
                body_text = f"{icon} **{sev.upper()}**: {c.get('message', '')}"
                if c.get("code_snippet"):
                    body_text += f"\n\n**Code:**\n```\n{c.get('code_snippet')}\n```"

                formatted.append({
                    "body": body_text,
                    "path": c.get("file", ""),
                    "new_position": c.get("line", 1),
                })

            # Build review body
            body = f"{self.config.bot_emoji} **{self.config.bot_name} - Inline Comments**\n\n"
            body += f"Found **{len(comments)}** item(s):\n"
            for sev, icon in icons.items():
                if severity_counts.get(sev, 0) > 0:
                    body += f"- {icon} {sev.title()}: {severity_counts[sev]}\n"

            url = f"{self.config.gitea_url}/api/v1/repos/{repo_name}/pulls/{pr_number}/reviews"
            payload = {"body": body, "commit_id": head_sha, "comments": formatted}

            try:
                response = requests.post(url, headers=self.headers, json=payload)
                if response.status_code in (200, 201):
                    print(f"Posted review with {len(comments)} inline comments")
                else:
                    print(f"Failed to post review: {response.status_code} {response.text}")
            except Exception as e:
                print(f"Error posting review: {e}")

        # Post summary comment
        if summaries or impact_context:
            combined = {
                "overview": " ".join(s.get("overview", "") for s in summaries),
                "strengths": [],
                "issues": [],
                "suggestions": [],
            }
            for s in summaries:
                combined["strengths"].extend(s.get("strengths", []))
                combined["issues"].extend(s.get("issues", []))
                combined["suggestions"].extend(s.get("suggestions", []))

            body = f"## {self.config.bot_emoji} {self.config.bot_name} Summary\n\n"

            # Narrative overview
            if combined["overview"]:
                body += f"{combined['overview']}\n\n"

            # Impact Analysis section (contextual impacts)
            if impact_context and impact_context.impacts:
                body += "### 🔍 Impact Analysis\n\n"
                body += "The following contextual impacts were identified:\n\n"

                for impact in impact_context.impacts[:5]:
                    body += f"**{impact.file_path}**"
                    if impact.change_summary:
                        body += f" — {impact.change_summary}"
                    body += "\n"

                    # Include the actual code that changed
                    if getattr(impact, "code_context", None):
                        body += f"```\n{impact.code_context}\n```\n"

                    if impact.potential_impacts:
                        for pi in impact.potential_impacts[:3]:
                            body += f"  - {pi}\n"

                    if impact.review_focus:
                        body += f"  - *Verify:* {impact.review_focus[0]}\n"

                    body += "\n"

                if impact_context.critical_files:
                    files_list = ", ".join(f"`{f}`" for f in impact_context.critical_files[:5])
                    body += f"**Files requiring attention:** {files_list}\n\n"

            # Findings narrative
            if combined["issues"] or comments:
                body += "### 📋 Findings\n\n"
                if comments:
                    # Group by severity for narrative
                    by_severity = {"critical": [], "error": [], "warning": [], "info": []}
                    for c in comments:
                        sev = c.get("severity", "info")
                        by_severity.setdefault(sev, []).append(c)

                    if by_severity["critical"]:
                        body += f"**Critical issues ({len(by_severity['critical'])}):** "
                        body += "These must be addressed before merging. "
                        body += "; ".join(c.get("message", "")[:80] + "..." if len(c.get("message", "")) > 80 else c.get("message", "") for c in by_severity["critical"][:2])
                        body += "\n\n"

                    if by_severity["error"]:
                        body += f"**Errors ({len(by_severity['error'])}):** "
                        body += "Bugs or incorrect behavior that need fixing. "
                        body += "See inline comments for details.\n\n"

                    if by_severity["warning"]:
                        body += f"**Warnings ({len(by_severity['warning'])}):** "
                        body += "Potential issues worth reviewing. "
                        body += "These won't block the PR but should be considered.\n\n"

                    if by_severity["info"]:
                        body += f"**Suggestions ({len(by_severity['info'])}):** "
                        body += "Minor improvements and optimizations identified.\n\n"

                elif combined["issues"]:
                    for i in combined["issues"][:5]:
                        body += f"- {i}\n"
                    body += "\n"

            # Strengths (keep brief)
            if combined["strengths"]:
                body += "### ✅ What's Good\n\n"
                body += " ".join(combined["strengths"][:3])
                body += "\n\n"

            # Actionable suggestions
            if combined["suggestions"]:
                body += "### 💡 Recommendations\n\n"
                for s in combined["suggestions"][:3]:
                    body += f"- {s}\n"
                body += "\n"

            body += "---\n*Generated by AI. Please review findings and use your judgment.*"

            url = f"{self.config.gitea_url}/api/v1/repos/{repo_name}/issues/{pr_number}/comments"
            try:
                response = requests.post(url, headers=self.headers, json={"body": body})
                if response.status_code in (200, 201):
                    print("Posted summary comment")
                else:
                    print(f"Failed to post summary: {response.status_code}")
            except Exception as e:
                print(f"Error posting summary: {e}")
