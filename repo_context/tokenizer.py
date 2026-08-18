from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol


class TokenEstimator(Protocol):
    name: str
    exact: bool
    description: str

    def count_text(self, text: str) -> int:
        ...


@dataclass(frozen=True)
class CallableEstimator:
    name: str
    callback: Callable[[str], int]
    exact: bool = False
    description: str = "Host-registered token estimator."

    def count_text(self, text: str) -> int:
        value = int(self.callback(text))
        return max(0, value)


@dataclass(frozen=True)
class NativeBytesEstimator:
    name: str = "native"
    exact: bool = False
    description: str = "Dependency-free UTF-8 bytes / 4 approximation."

    def count_text(self, text: str) -> int:
        size = len(text.encode("utf-8"))
        return max(1, (size + 3) // 4) if size else 0


class TiktokenEstimator:
    name = "tiktoken"
    exact = True
    description = "Optional tiktoken-backed estimator. Availability depends on the host environment."

    def __init__(self, *, model: str | None = None, encoding: str = "cl100k_base"):
        try:
            import tiktoken  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on host environment
            raise ValueError("tiktoken estimator requested but the optional 'tiktoken' package is not installed") from exc
        self.model = model
        self.encoding_name = encoding
        if model:
            try:
                self._encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                self._encoding = tiktoken.get_encoding(encoding)
        else:
            self._encoding = tiktoken.get_encoding(encoding)

    def count_text(self, text: str) -> int:
        return len(self._encoding.encode(text))


_REGISTRY: dict[str, TokenEstimator] = {"native": NativeBytesEstimator()}


def register_tokenizer(name: str, callback: Callable[[str], int], *, exact: bool = False,
                       description: str = "Host-registered token estimator.") -> None:
    """Register a process-local tokenizer without importing arbitrary modules from CLI input.

    Runtime hosts can inject a vendor/model-specific counter while the default package
    remains dependency-free. Registration is intentionally process-local and explicit.
    """
    key = str(name).strip().lower()
    if not key or key in {"native", "tiktoken"}:
        raise ValueError("custom tokenizer name must be non-empty and may not replace built-in names")
    _REGISTRY[key] = CallableEstimator(key, callback, exact=bool(exact), description=description)


def unregister_tokenizer(name: str) -> None:
    key = str(name).strip().lower()
    if key == "native":
        raise ValueError("native tokenizer cannot be removed")
    _REGISTRY.pop(key, None)


def _tiktoken_available() -> bool:
    try:
        import tiktoken  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


def tokenizer_status() -> list[dict[str, Any]]:
    items = [
        {
            "name": estimator.name,
            "available": True,
            "exact": bool(estimator.exact),
            "description": estimator.description,
            "source": "builtin" if name == "native" else "host-registered",
        }
        for name, estimator in sorted(_REGISTRY.items())
    ]
    items.append({
        "name": "tiktoken",
        "available": _tiktoken_available(),
        "exact": True,
        "description": TiktokenEstimator.description,
        "source": "optional-package",
    })
    return items


def get_tokenizer(name: str = "native", *, model: str | None = None,
                  encoding: str = "cl100k_base") -> TokenEstimator:
    key = str(name or "native").strip().lower()
    if key == "tiktoken":
        return TiktokenEstimator(model=model, encoding=encoding)
    estimator = _REGISTRY.get(key)
    if estimator is None:
        raise ValueError(f"Unknown tokenizer: {name}")
    return estimator


def token_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def count_tokens(value: Any, *, tokenizer: str = "native", model: str | None = None,
                 encoding: str = "cl100k_base") -> int:
    estimator = get_tokenizer(tokenizer, model=model, encoding=encoding)
    return estimator.count_text(token_text(value))


def token_estimate(value: Any, *, tokenizer: str = "native", model: str | None = None,
                   encoding: str = "cl100k_base") -> dict[str, Any]:
    estimator = get_tokenizer(tokenizer, model=model, encoding=encoding)
    return {
        "tokens": estimator.count_text(token_text(value)),
        "tokenizer": estimator.name,
        "exact": bool(estimator.exact),
        "model": model,
        "encoding": getattr(estimator, "encoding_name", None),
        "description": estimator.description,
    }
