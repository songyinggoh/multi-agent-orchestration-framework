"""Orchestra LLM providers."""

from orchestra.providers.http import HttpProvider

__all__ = ["HttpProvider"]


# Lazy imports for optional providers
def __getattr__(name: str) -> object:
    if name == "AnthropicProvider":
        from orchestra.providers.anthropic import AnthropicProvider
        return AnthropicProvider
    if name == "GoogleProvider":
        from orchestra.providers.google import GoogleProvider
        return GoogleProvider
    if name == "OllamaProvider":
        from orchestra.providers.ollama import OllamaProvider
        return OllamaProvider
    raise AttributeError(f"module 'orchestra.providers' has no attribute {name!r}")
