"""AI provider clients for code review."""

import json
from abc import ABC, abstractmethod

from config import Config


class AIClient(ABC):
    """Base class for AI clients."""

    @abstractmethod
    def review(self, system_prompt: str, user_message: str) -> dict:
        """Send review request and return parsed response."""
        pass


class OpenAIClient(AIClient):
    """OpenAI API client using Responses API for Codex models."""

    def __init__(self, config: Config, api_key: str):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.config = config

    def review(self, system_prompt: str, user_message: str) -> dict:
        review_schema = {
            "type": "object",
            "properties": {
                "inline_comments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string"},
                            "line": {"type": "integer"},
                            "severity": {"type": "string", "enum": ["info", "warning", "error", "critical"]},
                            "message": {"type": "string"}
                        },
                        "required": ["file", "line", "severity", "message"],
                        "additionalProperties": False
                    }
                },
                "summary": {
                    "type": "object",
                    "properties": {
                        "overview": {"type": "string"},
                        "strengths": {"type": "array", "items": {"type": "string"}},
                        "issues": {"type": "array", "items": {"type": "string"}},
                        "suggestions": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["overview", "strengths", "issues", "suggestions"],
                    "additionalProperties": False
                }
            },
            "required": ["inline_comments", "summary"],
            "additionalProperties": False
        }

        try:
            response = self.client.responses.create(
                model=self.config.model,
                instructions=system_prompt,
                input=user_message,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "code_review",
                        "strict": True,
                        "schema": review_schema
                    }
                }
            )
            return json.loads(response.output_text)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {e}")
            return {"inline_comments": [], "summary": {"overview": "Parse error", "strengths": [], "issues": [], "suggestions": []}}
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            raise


class AnthropicClient(AIClient):
    """Anthropic Claude API client."""

    def __init__(self, config: Config, api_key: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.config = config

    def review(self, system_prompt: str, user_message: str) -> dict:
        try:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            content = response.content[0].text
            # Try to extract JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {e}")
            return {"inline_comments": [], "summary": {"overview": "Parse error", "strengths": [], "issues": [], "suggestions": []}}
        except Exception as e:
            print(f"Error calling Anthropic API: {e}")
            raise


class OllamaClient(AIClient):
    """Ollama local model client."""

    def __init__(self, config: Config):
        import requests
        self.config = config
        self.base_url = config.ollama_url

    def review(self, system_prompt: str, user_message: str) -> dict:
        import requests
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.config.model,
                    "prompt": f"{system_prompt}\n\n{user_message}",
                    "stream": False,
                    "format": "json"
                },
                timeout=300
            )
            response.raise_for_status()
            content = response.json().get("response", "")
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {e}")
            return {"inline_comments": [], "summary": {"overview": "Parse error", "strengths": [], "issues": [], "suggestions": []}}
        except Exception as e:
            print(f"Error calling Ollama API: {e}")
            raise


def create_client(config: Config, api_key: str = None) -> AIClient:
    """Factory function to create the appropriate AI client."""
    if config.provider == "openai":
        if not api_key:
            raise ValueError("OPENAI_API_KEY required for OpenAI provider")
        return OpenAIClient(config, api_key)
    elif config.provider == "anthropic":
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY required for Anthropic provider")
        return AnthropicClient(config, api_key)
    elif config.provider == "ollama":
        return OllamaClient(config)
    else:
        raise ValueError(f"Unknown provider: {config.provider}")
