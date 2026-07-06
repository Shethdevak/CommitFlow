from abc import ABC, abstractmethod

class AIProvider(ABC):
    """Abstract interface defining required behaviors for AI Classifier Providers."""

    @abstractmethod
    def classify(self, prompt: str) -> str:
        """Sends a classification prompt to the AI provider and returns the raw response text.
        
        Args:
            prompt: The formatted prompt detailing commits, changed files, and target Features.
            
        Returns:
            The raw text response from the model, expected to be JSON.
        """
        pass
