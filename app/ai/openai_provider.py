import requests
from loguru import logger
from app.ai.provider import AIProvider
from app.utils.helpers import with_retry

class OpenAIProvider(AIProvider):
    """Integrates OpenAI chat completion models for task log classification."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        if not api_key:
            raise ValueError("OpenAI API key must be provided.")
        self.api_key = api_key
        self.model = model
        self.url = "https://api.openai.com/v1/chat/completions"

    @with_retry()
    def classify(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert software engineer assistant. You classify daily developer commits and source code modifications into Redmine Parent Features. You must output valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }

        logger.info(f"Sending classification prompt to OpenAI ({self.model})...")
        response = requests.post(self.url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        result = data["choices"][0]["message"]["content"]
        return result
