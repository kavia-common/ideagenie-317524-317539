"""
AI provider abstraction.

If no API key is configured, we return deterministic pseudo-ideas so the app
works in any environment (including CI) without external API calls.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class AIResult:
    """A normalized result from any provider."""

    provider: str
    model: Optional[str]
    ideas: List[str]


class AIProviderError(RuntimeError):
    """Raised when an AI provider fails to generate ideas."""


def _deterministic_ideas(topic: str, n: int) -> List[str]:
    """Create deterministic ideas from a topic using hashing.

    This produces stable output across runs for the same (topic, n), ensuring
    tests and demos behave consistently without external dependencies.
    """
    base = topic.strip() or "General"
    h = hashlib.sha256(base.encode("utf-8")).hexdigest()
    seeds = [h[i : i + 8] for i in range(0, min(len(h), n * 8), 8)]
    # If topic is very short, pad with more hash material
    while len(seeds) < n:
        h = hashlib.sha256(h.encode("utf-8")).hexdigest()
        seeds.extend([h[i : i + 8] for i in range(0, min(len(h), (n - len(seeds)) * 8), 8)])

    templates = [
        "Create a simple MVP for '{topic}' focused on {seed} and validate with 5 users.",
        "Write a step-by-step checklist for '{topic}' and automate the {seed} step first.",
        "Generate 3 surprising constraints for '{topic}' (seed {seed}) to spark novelty.",
        "Turn '{topic}' into a 7-day challenge; day {day} emphasizes {seed}.",
        "Design a one-page explainer for '{topic}' aimed at beginners; emphasize {seed}.",
        "Combine '{topic}' with an adjacent domain (seed {seed}) to produce a hybrid concept.",
        "Brainstorm a 'do less' version of '{topic}' removing everything except {seed}.",
        "Draft an experiment for '{topic}' with a clear metric; use {seed} as the key variable.",
    ]

    ideas: List[str] = []
    for idx in range(n):
        seed = seeds[idx]
        t = templates[idx % len(templates)]
        day = (idx % 7) + 1
        ideas.append(t.format(topic=base, seed=seed, day=day))
    return ideas


# PUBLIC_INTERFACE
def generate_ideas(topic: str, n_ideas: int = 7) -> AIResult:
    """Generate ideas for a topic.

    If no AI key is configured, uses deterministic fallback generation.

    Environment variables (optional):
      - OPENAI_API_KEY: when set, may be used by a real provider in future.
      - AI_PROVIDER: reserved for future (e.g., 'openai'); currently only fallback is implemented.
    """
    # Deterministic fallback if no key configured
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        return AIResult(provider="fallback", model=None, ideas=_deterministic_ideas(topic, n_ideas))

    # For now, we intentionally avoid adding external network dependencies.
    # If an API key is present, still use deterministic fallback to keep the
    # project self-contained unless extended later.
    return AIResult(provider="fallback", model=None, ideas=_deterministic_ideas(topic, n_ideas))
