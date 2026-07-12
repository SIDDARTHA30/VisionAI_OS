from typing import Dict
from app.providers.base_provider import BaseProvider
from app.providers.gemini_provider import GeminiProvider


class ProviderRegistry:
    """Registry to manage and resolve instances of BaseProvider adapters."""

    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}

    def register(self, name: str, provider: BaseProvider) -> None:
        """Register a new provider instance under a key name."""
        self._providers[name.lower()] = provider

    def get(self, name: str) -> BaseProvider:
        """Retrieve a registered provider by name."""
        provider = self._providers.get(name.lower())
        if not provider:
            raise KeyError(f"AI Provider '{name}' is not registered.")
        return provider

    def list_providers(self) -> list[str]:
        """List all currently registered provider keys."""
        return list(self._providers.keys())


# Global registry instance
provider_registry = ProviderRegistry()

# Register default Gemini provider
provider_registry.register("gemini", GeminiProvider())
