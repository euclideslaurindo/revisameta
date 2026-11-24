"""AI provider layer (docs/ia.md 7.15.5; ADR-007; stage 7 step 1).

One small interface, several interchangeable adapters chosen by configuration: the
rest of the system never talks to a vendor directly. Every answer that feeds a
suggestion is structured and validated against a Pydantic schema; anything outside
the schema is discarded (7.15.3, rule 4). The AI never computes statistics and never
decides: callers only use it to explain or to point at text.
"""

from typing import Protocol

from pydantic import BaseModel, ValidationError


class AIError(Exception):
    """Base error. `code` is an i18n key the screen can show."""

    code = "ai.failed"


class AIUnavailableError(AIError):
    """No provider configured (e.g. no key yet): the feature is off, nothing breaks."""

    code = "ai.unavailable"


class AIQuotaExceededError(AIError):
    """The provider's free quota (or ours) is used up until it renews."""

    code = "ai.quota_exceeded"


class AIInvalidOutputError(AIError):
    """The answer did not follow the schema: it is discarded, never shown as data."""

    code = "ai.invalid_output"


class AIProvider(Protocol):
    name: str
    model: str

    async def complete(self, system: str, prompt: str) -> str: ...

    async def complete_structured[T: BaseModel](
        self, system: str, prompt: str, schema: type[T]
    ) -> T: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def parse_structured[T: BaseModel](raw: str, schema: type[T]) -> T:
    """Validates a JSON answer; raises AIInvalidOutputError instead of guessing."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        return schema.model_validate_json(text)
    except ValidationError as error:
        raise AIInvalidOutputError(str(error)) from error
