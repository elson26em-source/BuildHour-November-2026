from __future__ import annotations

import os
from typing import Any

import requests

from src.config.schema import Config, LLMConfig

DEFAULT_TIMEOUT_SECONDS = 30.0


class LLMError(RuntimeError):
    """Raised when an LLM provider request fails."""


class LLMClient:
    provider = "base"

    def __init__(
        self,
        llm_config: LLMConfig,
        *,
        session: Any | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.llm_config = llm_config
        self.model = llm_config.model
        self.timeout = timeout
        self.session = session or requests.Session()

    def _api_key(self) -> str:
        key = os.environ.get(self.llm_config.api_key_env)
        if not key:
            raise LLMError(
                f"Missing API key for LLM provider '{self.llm_config.provider}': "
                f"set {self.llm_config.api_key_env} in .env or the environment."
            )
        return key

    def _post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = self.session.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LLMError(
                f"LLM request to {self.llm_config.provider} failed: {exc}"
            ) from exc

        if response.status_code >= 400:
            detail = ""
            try:
                body = response.json()
                detail = str(
                    body.get("error", {}).get("message")
                    or body.get("error")
                    or body
                )
            except Exception:
                detail = response.text[:300]
            raise LLMError(
                f"LLM provider {self.llm_config.provider} returned HTTP "
                f"{response.status_code}: {detail}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError(
                f"LLM provider {self.llm_config.provider} returned invalid JSON."
            ) from exc
        if not isinstance(data, dict):
            raise LLMError(
                f"LLM provider {self.llm_config.provider} returned an "
                "unexpected response."
            )
        return data

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        raise NotImplementedError


class OpenAICompatibleClient(LLMClient):
    def __init__(
        self,
        llm_config: LLMConfig,
        *,
        provider: str,
        endpoint: str,
        session: Any | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(llm_config, session=session, timeout=timeout)
        self.provider = provider
        self.endpoint = endpoint

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        api_key = self._api_key()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": (
                self.llm_config.temperature
                if temperature is None
                else temperature
            ),
            "max_tokens": (
                self.llm_config.max_tokens
                if max_tokens is None
                else max_tokens
            ),
        }
        data = self._post_json(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                f"LLM provider {self.provider} returned a malformed response."
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMError(
                f"LLM provider {self.provider} returned an empty answer."
            )
        return content.strip()


class AnthropicClient(LLMClient):
    provider = "anthropic"
    endpoint = "https://api.anthropic.com/v1/messages"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        api_key = self._api_key()
        payload = {
            "model": self.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": (
                self.llm_config.temperature
                if temperature is None
                else temperature
            ),
            "max_tokens": (
                self.llm_config.max_tokens
                if max_tokens is None
                else max_tokens
            ),
        }
        data = self._post_json(
            self.endpoint,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload=payload,
        )
        try:
            blocks = data["content"]
            text = "".join(
                block.get("text", "")
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )
        except (KeyError, TypeError) as exc:
            raise LLMError(
                "LLM provider anthropic returned a malformed response."
            ) from exc
        if not text.strip():
            raise LLMError("LLM provider anthropic returned an empty answer.")
        return text.strip()


class GeminiClient(LLMClient):
    provider = "gemini"
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{model}:generateContent"
    )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        api_key = self._api_key()
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {"role": "user", "parts": [{"text": user_prompt}]}
            ],
            "generationConfig": {
                "temperature": (
                    self.llm_config.temperature
                    if temperature is None
                    else temperature
                ),
                "maxOutputTokens": (
                    self.llm_config.max_tokens
                    if max_tokens is None
                    else max_tokens
                ),
            },
        }
        data = self._post_json(
            self.endpoint.format(model=self.model),
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            payload=payload,
        )
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(
                part.get("text", "")
                for part in parts
                if isinstance(part, dict)
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                "LLM provider gemini returned a malformed response."
            ) from exc
        if not text.strip():
            raise LLMError("LLM provider gemini returned an empty answer.")
        return text.strip()


def create_llm_client(
    config: Config | LLMConfig,
    *,
    session: Any | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> LLMClient:
    llm_config = config.llm if isinstance(config, Config) else config
    provider = llm_config.provider.lower()

    if provider == "groq":
        return OpenAICompatibleClient(
            llm_config,
            provider="groq",
            endpoint="https://api.groq.com/openai/v1/chat/completions",
            session=session,
            timeout=timeout,
        )
    if provider == "openai":
        return OpenAICompatibleClient(
            llm_config,
            provider="openai",
            endpoint="https://api.openai.com/v1/chat/completions",
            session=session,
            timeout=timeout,
        )
    if provider == "mistral":
        return OpenAICompatibleClient(
            llm_config,
            provider="mistral",
            endpoint="https://api.mistral.ai/v1/chat/completions",
            session=session,
            timeout=timeout,
        )
    if provider == "anthropic":
        return AnthropicClient(
            llm_config,
            session=session,
            timeout=timeout,
        )
    if provider == "gemini":
        return GeminiClient(
            llm_config,
            session=session,
            timeout=timeout,
        )

    raise LLMError(f"Unsupported LLM provider: {llm_config.provider!r}.")
