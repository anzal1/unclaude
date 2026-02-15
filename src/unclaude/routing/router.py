"""Smart model router.

Selects the optimal LLM model for each request based on:
- Request complexity tier (from scorer)
- Routing profile (auto/eco/premium/free)
- Provider availability and fallback chains
- Session model pinning (continuity within a conversation)
- Cost tracking

Inspired by ClawRouter's 15-dimension scoring, adapted for
unclaude's provider-agnostic LiteLLM backend.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .scorer import RequestScorer, RequestTier, ScoringResult


class RoutingProfile(str, Enum):
    """Routing profiles controlling cost vs quality trade-off."""
    AUTO = "auto"          # Balanced - smart selection per request
    ECO = "eco"            # Minimize cost, use smaller models
    PREMIUM = "premium"    # Always use best available model
    FREE = "free"          # Only use free/local models


@dataclass
class ModelSpec:
    """A model specification with metadata."""
    model_id: str       # LiteLLM model identifier
    provider: str       # Provider name (openai, anthropic, etc.)
    tier: RequestTier   # What tier this model handles
    cost_per_1k: float  # Approximate cost per 1K tokens (input)
    supports_tools: bool = True
    max_context: int = 128_000
    is_free: bool = False
    is_local: bool = False


@dataclass
class RoutingDecision:
    """The result of a routing decision."""
    model_id: str
    provider: str
    tier: RequestTier
    profile: RoutingProfile
    scoring: ScoringResult
    estimated_cost_per_1k: float
    fallback_models: list[str] = field(default_factory=list)
    pinned: bool = False  # If True, was pinned from session


# Default model tiers - these can be overridden via config
DEFAULT_MODEL_TIERS: dict[RequestTier, list[ModelSpec]] = {
    RequestTier.SIMPLE: [
        ModelSpec("gpt-4o-mini", "openai", RequestTier.SIMPLE,
                  0.00015, max_context=128_000),
        ModelSpec("claude-3-5-haiku-20241022",
                  "anthropic", RequestTier.SIMPLE, 0.0008),
        ModelSpec("gemini/gemini-2.0-flash", "gemini",
                  RequestTier.SIMPLE, 0.0001, max_context=1_000_000),
    ],
    RequestTier.MEDIUM: [
        ModelSpec("gpt-4o", "openai", RequestTier.MEDIUM, 0.0025),
        ModelSpec("claude-sonnet-4-20250514",
                  "anthropic", RequestTier.MEDIUM, 0.003),
        ModelSpec("gemini/gemini-2.5-flash", "gemini",
                  RequestTier.MEDIUM, 0.00015, max_context=1_000_000),
    ],
    RequestTier.COMPLEX: [
        ModelSpec("claude-sonnet-4-20250514", "anthropic",
                  RequestTier.COMPLEX, 0.003),
        ModelSpec("gpt-4o", "openai", RequestTier.COMPLEX, 0.0025),
        ModelSpec("gemini/gemini-2.5-pro", "gemini",
                  RequestTier.COMPLEX, 0.00125, max_context=1_000_000),
    ],
    RequestTier.REASONING: [
        ModelSpec("claude-opus-4-20250514", "anthropic",
                  RequestTier.REASONING, 0.015),
        ModelSpec("o3", "openai", RequestTier.REASONING, 0.010),
        ModelSpec("gemini/gemini-2.5-pro", "gemini",
                  RequestTier.REASONING, 0.00125, max_context=1_000_000),
    ],
}

# Eco mode overrides - use cheaper models
ECO_OVERRIDES: dict[RequestTier, str] = {
    RequestTier.SIMPLE: "gemini/gemini-2.0-flash",
    RequestTier.MEDIUM: "gemini/gemini-2.5-flash",
    RequestTier.COMPLEX: "gpt-4o-mini",
    RequestTier.REASONING: "gemini/gemini-2.5-pro",
}

# Premium mode overrides - use best models
PREMIUM_OVERRIDES: dict[RequestTier, str] = {
    RequestTier.SIMPLE: "claude-sonnet-4-20250514",
    RequestTier.MEDIUM: "claude-sonnet-4-20250514",
    RequestTier.COMPLEX: "claude-opus-4-20250514",
    RequestTier.REASONING: "claude-opus-4-20250514",
}

# Free/local models only
FREE_MODELS: list[ModelSpec] = [
    ModelSpec("ollama/llama3.1", "ollama", RequestTier.MEDIUM,
              0.0, is_free=True, is_local=True),
    ModelSpec("ollama/codellama", "ollama", RequestTier.MEDIUM,
              0.0, is_free=True, is_local=True, max_context=16_000),
    ModelSpec("ollama/deepseek-coder-v2", "ollama",
              RequestTier.COMPLEX, 0.0, is_free=True, is_local=True),
    ModelSpec("gemini/gemini-2.0-flash", "gemini",
              RequestTier.SIMPLE, 0.0, is_free=True),
]


class SmartRouter:
    """Routes requests to optimal models based on complexity.

    Usage:
        router = SmartRouter()
        decision = router.route("Fix the bug in auth.py", profile=RoutingProfile.AUTO)
        # decision.model_id = "claude-sonnet-4-20250514"
        # decision.tier = RequestTier.MEDIUM
    """

    def __init__(
        self,
        model_tiers: dict[RequestTier, list[ModelSpec]] | None = None,
        default_profile: RoutingProfile = RoutingProfile.AUTO,
        preferred_provider: str | None = None,
    ):
        self.scorer = RequestScorer()
        self.model_tiers = model_tiers or DEFAULT_MODEL_TIERS
        self.default_profile = default_profile
        self.preferred_provider = preferred_provider

        # Session pinning: conversation_id → model_id
        self._session_pins: dict[str, str] = {}

        # Cost tracking
        self._total_cost: float = 0.0
        self._request_count: int = 0

    def route(
        self,
        message: str,
        profile: RoutingProfile | None = None,
        conversation_depth: int = 0,
        conversation_id: str | None = None,
        has_tools: bool = True,
        require_tools: bool = False,
    ) -> RoutingDecision:
        """Route a request to the optimal model.

        Args:
            message: User's message text.
            profile: Routing profile (default: instance default).
            conversation_depth: Number of turns so far.
            conversation_id: For session pinning.
            has_tools: Whether tools are available.
            require_tools: If True, only select models with tool support.

        Returns:
            RoutingDecision with model selection and metadata.
        """
        profile = profile or self.default_profile

        # Check session pin first
        if conversation_id and conversation_id in self._session_pins:
            pinned_model = self._session_pins[conversation_id]
            scoring = self.scorer.score(message, conversation_depth, has_tools)
            return RoutingDecision(
                model_id=pinned_model,
                provider=self._infer_provider(pinned_model),
                tier=scoring.tier,
                profile=profile,
                scoring=scoring,
                estimated_cost_per_1k=0.0,
                pinned=True,
            )

        # Score the request
        scoring = self.scorer.score(message, conversation_depth, has_tools)

        # Select model based on profile
        if profile == RoutingProfile.FREE:
            return self._route_free(scoring, profile, require_tools)
        elif profile == RoutingProfile.ECO:
            return self._route_eco(scoring, profile)
        elif profile == RoutingProfile.PREMIUM:
            return self._route_premium(scoring, profile)
        else:  # AUTO
            return self._route_auto(scoring, profile, require_tools)

    def pin_session(self, conversation_id: str, model_id: str) -> None:
        """Pin a conversation to a specific model for continuity."""
        self._session_pins[conversation_id] = model_id

    def unpin_session(self, conversation_id: str) -> None:
        """Remove session model pin."""
        self._session_pins.pop(conversation_id, None)

    def track_cost(self, tokens_used: int, cost_per_1k: float) -> None:
        """Track cost of a completed request."""
        self._total_cost += (tokens_used / 1000) * cost_per_1k
        self._request_count += 1

    @property
    def stats(self) -> dict[str, Any]:
        """Get routing statistics."""
        return {
            "total_cost": self._total_cost,
            "request_count": self._request_count,
            "avg_cost_per_request": (
                self._total_cost / self._request_count
                if self._request_count > 0 else 0
            ),
            "active_session_pins": len(self._session_pins),
        }

    def _route_auto(
        self,
        scoring: ScoringResult,
        profile: RoutingProfile,
        require_tools: bool,
    ) -> RoutingDecision:
        """Auto routing - smart selection per request."""
        tier = scoring.tier
        candidates = self.model_tiers.get(tier, [])

        if require_tools:
            candidates = [m for m in candidates if m.supports_tools]

        if not candidates:
            # Fallback: try MEDIUM tier
            candidates = self.model_tiers.get(RequestTier.MEDIUM, [])

        # Prefer provider if specified
        if self.preferred_provider and candidates:
            preferred = [m for m in candidates if m.provider ==
                         self.preferred_provider]
            if preferred:
                candidates = preferred + \
                    [m for m in candidates if m.provider != self.preferred_provider]

        selected = candidates[0] if candidates else ModelSpec(
            "gpt-4o-mini", "openai", RequestTier.SIMPLE, 0.00015,
        )

        fallbacks = [m.model_id for m in candidates[1:3]]

        return RoutingDecision(
            model_id=selected.model_id,
            provider=selected.provider,
            tier=tier,
            profile=profile,
            scoring=scoring,
            estimated_cost_per_1k=selected.cost_per_1k,
            fallback_models=fallbacks,
        )

    def _route_eco(
        self,
        scoring: ScoringResult,
        profile: RoutingProfile,
    ) -> RoutingDecision:
        """Eco routing - minimize cost."""
        tier = scoring.tier
        model_id = ECO_OVERRIDES.get(tier, "gemini/gemini-2.0-flash")

        return RoutingDecision(
            model_id=model_id,
            provider=self._infer_provider(model_id),
            tier=tier,
            profile=profile,
            scoring=scoring,
            estimated_cost_per_1k=0.0001,  # Eco models are cheap
        )

    def _route_premium(
        self,
        scoring: ScoringResult,
        profile: RoutingProfile,
    ) -> RoutingDecision:
        """Premium routing - use best models."""
        tier = scoring.tier
        model_id = PREMIUM_OVERRIDES.get(tier, "claude-opus-4-20250514")

        return RoutingDecision(
            model_id=model_id,
            provider=self._infer_provider(model_id),
            tier=tier,
            profile=profile,
            scoring=scoring,
            estimated_cost_per_1k=0.015,
        )

    def _route_free(
        self,
        scoring: ScoringResult,
        profile: RoutingProfile,
        require_tools: bool,
    ) -> RoutingDecision:
        """Free routing - only free/local models."""
        candidates = FREE_MODELS
        if require_tools:
            candidates = [m for m in candidates if m.supports_tools]

        # Pick best match for tier
        tier_match = [m for m in candidates if m.tier == scoring.tier]
        selected = (tier_match or candidates or [ModelSpec(
            "ollama/llama3.1", "ollama", RequestTier.MEDIUM, 0.0, is_free=True, is_local=True,
        )])[0]

        return RoutingDecision(
            model_id=selected.model_id,
            provider=selected.provider,
            tier=scoring.tier,
            profile=profile,
            scoring=scoring,
            estimated_cost_per_1k=0.0,
        )

    @staticmethod
    def _infer_provider(model_id: str) -> str:
        """Infer provider from model ID."""
        if model_id.startswith("gemini/"):
            return "gemini"
        elif model_id.startswith("ollama/"):
            return "ollama"
        elif "claude" in model_id:
            return "anthropic"
        elif "gpt" in model_id or model_id.startswith("o"):
            return "openai"
        else:
            return "unknown"
