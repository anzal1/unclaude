"""Request scoring for smart routing.

Analyzes a request across multiple dimensions to determine its
complexity tier. This is all done locally with regex/heuristics -
no LLM calls needed for routing decisions.

Dimensions (from ClawRouter, adapted):
1. Token length (input size)
2. Code presence (code blocks, file references)
3. Reasoning markers (prove, analyze, compare, explain why)
4. Tool usage signals (file operations, bash commands)
5. Domain complexity (math, architecture, security)
6. Conversation depth (how many turns so far)
7. Output expectations (short answer vs long generation)
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RequestTier(str, Enum):
    """Complexity tiers for routing.

    Each tier maps to different model quality/cost levels.
    """
    SIMPLE = "simple"       # Trivial queries, quick answers
    MEDIUM = "medium"       # Standard coding tasks
    COMPLEX = "complex"     # Multi-file changes, architecture
    REASONING = "reasoning"  # Deep analysis, proofs, debugging


@dataclass
class ScoringResult:
    """Result of scoring a request."""
    tier: RequestTier
    confidence: float  # 0.0 to 1.0
    scores: dict[str, float] = field(default_factory=dict)
    explanation: str = ""


# Regex patterns for scoring dimensions
REASONING_MARKERS = re.compile(
    r'\b(prove|analyze|compare|explain\s+why|reason|debug|trade-?offs?|'
    r'pros?\s+(?:and|&)\s+cons?|justify|evaluate|critique|assess|'
    r'what\s+(?:would|could)\s+happen|implications?|consequences?|'
    r'root\s+cause|deep\s+dive|architecture|design\s+pattern)\b',
    re.IGNORECASE,
)

CODE_MARKERS = re.compile(
    r'(```[\s\S]*?```|`[^`]+`|\.py\b|\.ts\b|\.js\b|\.go\b|\.rs\b|'
    r'function\s|class\s|def\s|import\s|require\(|'
    r'refactor|implement|fix\s+(?:the\s+)?bug|write\s+(?:a\s+)?(?:test|function|class)|'
    r'create\s+(?:a\s+)?(?:file|module|component|api))',
    re.IGNORECASE,
)

SIMPLE_MARKERS = re.compile(
    r'^(what\s+is|who\s+is|when\s+was|where\s+is|how\s+many|'
    r'list\s+|show\s+me|tell\s+me|what\s+does|'
    r'yes|no|ok|thanks|hi|hello|help|version)\s*\??$',
    re.IGNORECASE,
)

AGENTIC_MARKERS = re.compile(
    r'\b(build|create|implement|develop|write|deploy|setup|configure|'
    r'test|debug|fix|refactor|optimize|migrate|upgrade|'
    r'step\s+by\s+step|multi|parallel|automate|pipeline|workflow)\b',
    re.IGNORECASE,
)

MATH_MARKERS = re.compile(
    r'(\b(?:equation|formula|integral|derivative|matrix|vector|'
    r'probability|statistics|theorem|proof|induction|'
    r'O\(n|complexity|algorithm)\b|[∫∑∏√±×÷≠≤≥])',
    re.IGNORECASE,
)


class RequestScorer:
    """Scores requests across multiple dimensions for routing.

    All scoring is local - no LLM calls. Uses regex, heuristics,
    and simple features.
    """

    # Dimension weights (tune these based on routing accuracy)
    WEIGHTS = {
        "length": 0.10,
        "code": 0.20,
        "reasoning": 0.25,
        "agentic": 0.20,
        "math": 0.10,
        "depth": 0.05,
        "simplicity": 0.10,
    }

    def score(
        self,
        message: str,
        conversation_depth: int = 0,
        has_tools: bool = True,
    ) -> ScoringResult:
        """Score a request to determine its complexity tier.

        Args:
            message: The user's message.
            conversation_depth: Number of turns so far.
            has_tools: Whether tools are available.

        Returns:
            ScoringResult with tier and confidence.
        """
        scores: dict[str, float] = {}

        # 1. Length score (longer = more complex)
        char_count = len(message)
        scores["length"] = min(1.0, char_count / 2000)

        # 2. Code presence
        code_matches = len(CODE_MARKERS.findall(message))
        scores["code"] = min(1.0, code_matches / 3)

        # 3. Reasoning markers
        reasoning_matches = len(REASONING_MARKERS.findall(message))
        scores["reasoning"] = min(1.0, reasoning_matches / 2)

        # 4. Agentic markers (multi-step tasks)
        agentic_matches = len(AGENTIC_MARKERS.findall(message))
        scores["agentic"] = min(1.0, agentic_matches / 3)

        # 5. Math/formal reasoning
        math_matches = len(MATH_MARKERS.findall(message))
        scores["math"] = min(1.0, math_matches / 2)

        # 6. Conversation depth
        scores["depth"] = min(1.0, conversation_depth / 20)

        # 7. Simplicity (inverse - high = simple)
        scores["simplicity"] = 1.0 if SIMPLE_MARKERS.match(
            message.strip()) else 0.0

        # Calculate weighted score
        weighted = sum(
            scores[dim] * self.WEIGHTS[dim]
            for dim in scores
        )

        # Determine tier
        tier, confidence = self._classify(weighted, scores)

        return ScoringResult(
            tier=tier,
            confidence=confidence,
            scores=scores,
            explanation=self._explain(scores, tier),
        )

    def _classify(
        self,
        weighted_score: float,
        scores: dict[str, float],
    ) -> tuple[RequestTier, float]:
        """Classify into a tier based on weighted score.

        Special rules:
        - 2+ reasoning markers → REASONING at 0.97 confidence
        - Simplicity detected → SIMPLE at 0.95 confidence
        - High agentic score → COMPLEX (needs good tool use)
        """
        # Special rules (from ClawRouter)
        if scores.get("reasoning", 0) > 0.8:
            return RequestTier.REASONING, 0.97

        if scores.get("simplicity", 0) > 0.5:
            return RequestTier.SIMPLE, 0.95

        if scores.get("math", 0) > 0.5:
            return RequestTier.REASONING, 0.90

        # Score-based classification
        if weighted_score < 0.15:
            return RequestTier.SIMPLE, 0.85
        elif weighted_score < 0.35:
            return RequestTier.MEDIUM, 0.80
        elif weighted_score < 0.55:
            return RequestTier.COMPLEX, 0.75
        else:
            return RequestTier.REASONING, 0.70

    def _explain(self, scores: dict[str, float], tier: RequestTier) -> str:
        """Generate a human-readable explanation of the scoring."""
        top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        factors = ", ".join(f"{k}={v:.2f}" for k, v in top if v > 0)
        return f"Tier={tier.value} (factors: {factors})"
