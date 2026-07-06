import requests
from loguru import logger
from app.ai.provider import AIProvider
from app.utils.helpers import with_retry

class OpenRouterProvider(AIProvider):
    """Integrates OpenRouter Chat Completion API for model accessibility."""

    def __init__(self, api_key: str, model: str = "meta-llama/llama-3.1-70b-instruct"):
        if not api_key:
            raise ValueError("OpenRouter API key must be provided.")
        self.api_key = api_key
        self.model = model
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    @with_retry()
    def classify(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/google/devsync",  # Required by OpenRouter rules
            "X-Title": "DevSync Worklog Automator"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an expert software engineer assistant. You classify daily developer commits and "
                        "source code modifications into Redmine Parent Features. You must output valid JSON. "
                        "Do not wrap your response in markdown code blocks, return only the JSON string."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }

        logger.info(f"Sending classification prompt to OpenRouter ({self.model})...")
        response = requests.post(self.url, headers=headers, json=payload, timeout=35)
        response.raise_for_status()
        
        data = response.json()
        result = data["choices"][0]["message"]["content"]
        return result
