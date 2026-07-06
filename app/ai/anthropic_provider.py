import requests
from loguru import logger
from app.ai.provider import AIProvider
from app.utils.helpers import with_retry

class AnthropicProvider(AIProvider):
    """Integrates Anthropic Claude models for classification of developer commits."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20240620"):
        if not api_key:
            raise ValueError("Anthropic API key must be provided.")
        self.api_key = api_key
        self.model = model
        self.url = "https://api.anthropic.com/v1/messages"

    @with_retry()
    def classify(self, prompt: str) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        system_instruction = (
            "You are an expert software engineer assistant. You classify daily developer commits and "
            "source code modifications into Redmine Parent Features. You must output ONLY valid JSON. "
            "Do not wrap your response in markdown markers like ```json ... ```. Just return raw JSON."
        )

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system_instruction,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1
        }

        logger.info(f"Sending classification prompt to Anthropic ({self.model})...")
        response = requests.post(self.url, headers=headers, json=payload, timeout=35)
        response.raise_for_status()
        
        data = response.json()
        try:
            result = data["content"][0]["text"]
            return result.strip()
        except (KeyError, IndexError) as e:
            logger.error(f"Malformed response format from Anthropic API: {data}")
            raise ValueError("Anthropic API returned an unexpected message structure.") from e
