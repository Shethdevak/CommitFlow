import requests
from loguru import logger
from app.ai.provider import AIProvider
from app.utils.helpers import with_retry

class OllamaProvider(AIProvider):
    """Integrates locally running Ollama models for secure offline classification."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.url = f"{self.base_url}/api/chat"

    @with_retry()
    def classify(self, prompt: str) -> str:
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
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.1
            }
        }

        logger.info(f"Sending classification prompt to Ollama ({self.model}) at {self.base_url}...")
        response = requests.post(self.url, json=payload, timeout=45)
        response.raise_for_status()
        
        data = response.json()
        try:
            result = data["message"]["content"]
            return result
        except KeyError as e:
            logger.error(f"Malformed response format from Ollama: {data}")
            raise ValueError("Ollama API returned an unexpected response structure.") from e
