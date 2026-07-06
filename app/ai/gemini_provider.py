import requests
from loguru import logger
from app.ai.provider import AIProvider
from app.utils.helpers import with_retry

class GeminiProvider(AIProvider):
    """Integrates Google Gemini models for commit classification via standard REST API."""

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        if not api_key:
            raise ValueError("Gemini API key must be provided.")
        self.api_key = api_key
        self.model = model

    @with_retry()
    def classify(self, prompt: str) -> str:
        # Construct Gemini API URL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Include instructions in system_instruction or directly inside prompt
        system_instruction = (
            "You are an expert software engineer assistant. You classify daily developer commits and "
            "source code modifications into Redmine Parent Features. You must output valid JSON."
        )
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_instruction}\n\nUser request:\n{prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1
            }
        }

        logger.info(f"Sending classification prompt to Gemini ({self.model})...")
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        try:
            result = data["candidates"][0]["content"]["parts"][0]["text"]
            return result
        except (KeyError, IndexError) as e:
            logger.error(f"Malformed response format from Gemini API: {data}")
            raise ValueError("Gemini API returned an unexpected response structure.") from e
