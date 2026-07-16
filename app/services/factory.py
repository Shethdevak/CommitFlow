"""Shared SyncService factory used by CLI and web API."""

from app.config.settings import Settings
from app.database.connection import init_db
from app.github.client import GitHubClient
from app.gitlab.client import GitLabClient
from app.redmine.client import RedmineClient
from app.mappings.resolver import MappingResolver
from app.ai.openai_provider import OpenAIProvider
from app.ai.gemini_provider import GeminiProvider
from app.ai.anthropic_provider import AnthropicProvider
from app.ai.openrouter_provider import OpenRouterProvider
from app.ai.ollama_provider import OllamaProvider
from app.ai.groq_provider import GroqProvider
from app.services.classifier import FeatureClassifierService
from app.services.sync import SyncService


def build_sync_service(settings: Settings) -> SyncService:
    """Initialize clients + classifier + SyncService from a Settings object."""
    init_db(settings.db_path)

    github_client = GitHubClient(token=settings.github_token)
    gitlab_client = GitLabClient(token=settings.gitlab_token, base_url=settings.gitlab_api_url)
    redmine_client = RedmineClient(base_url=settings.redmine_url, api_key=settings.redmine_api_key)

    mapping_resolver = MappingResolver(
        mappings_path=settings.mappings_path,
        match_threshold=settings.project_match_threshold,
    )

    provider_name = settings.ai_provider
    if provider_name == "openai":
        provider = OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_model)
    elif provider_name == "gemini":
        provider = GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
    elif provider_name == "anthropic":
        provider = AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    elif provider_name == "openrouter":
        provider = OpenRouterProvider(api_key=settings.openrouter_api_key, model=settings.openrouter_model)
    elif provider_name == "ollama":
        provider = OllamaProvider(base_url=settings.ollama_api_url, model=settings.ollama_model)
    elif provider_name == "groq":
        provider = GroqProvider(api_key=settings.groq_api_key, model=settings.groq_model)
    else:
        raise ValueError(f"Unknown AI provider '{provider_name}'")

    classifier_service = FeatureClassifierService(
        ai_provider=provider,
        confidence_threshold=settings.ai_confidence_threshold,
        default_feature=settings.default_feature,
    )

    return SyncService(
        settings=settings,
        github_client=github_client,
        gitlab_client=gitlab_client,
        redmine_client=redmine_client,
        mapping_resolver=mapping_resolver,
        classifier_service=classifier_service,
    )
