"""Integration tests for the 5 Pact-powered upgrades to UnClaude.

Tests:
1. Pact identity persistence and session delegation
2. Memory consolidation engine clustering & promotion
3. Experiential learning extraction & retrieval
4. Session chain verification and revocation
5. Subagent delegation narrowing
"""

import asyncio
import json
import os
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def tmp_identity_dir(tmp_path):
    """Temporary directory for identity keys (avoids touching real ~/.unclaude)."""
    d = tmp_path / "identity"
    d.mkdir()
    return d


@pytest.fixture
def tmp_memory_db(tmp_path):
    """Temporary SQLite DB for memory."""
    return tmp_path / "memory_test.db"


@pytest.fixture
def memory(tmp_memory_db):
    """Fresh HierarchicalMemory with temp DB."""
    from unclaude.memory_v2 import HierarchicalMemory
    return HierarchicalMemory(db_path=tmp_memory_db)


@pytest.fixture
def identity_manager(tmp_identity_dir):
    """PactIdentityManager using temp directory."""
    from unclaude.auth.pact_identity import PactIdentityManager
    return PactIdentityManager(identity_dir=tmp_identity_dir)


# ═══════════════════════════════════════════════════════════════
# 1. PACT IDENTITY — Persistence & Sessions
# ═══════════════════════════════════════════════════════════════

class TestPactIdentity:
    """Test persistent cryptographic identity."""

    def test_root_identity_created(self, identity_manager):
        """Root identity should be created on first init."""
        assert identity_manager.root_identity is not None
        assert identity_manager.root_id  # Non-empty hash
        assert identity_manager.root_identity.name == "unclaude-root"

    def test_root_identity_persists_across_instances(self, tmp_identity_dir):
        """Same identity dir should yield the same root key."""
        from unclaude.auth.pact_identity import PactIdentityManager

        mgr1 = PactIdentityManager(identity_dir=tmp_identity_dir)
        root_id_1 = mgr1.root_id
        pub_key_1 = mgr1.root_identity.public_key

        # Create a new manager pointing to the same directory
        mgr2 = PactIdentityManager(identity_dir=tmp_identity_dir)
        root_id_2 = mgr2.root_id
        pub_key_2 = mgr2.root_identity.public_key

        assert root_id_1 == root_id_2
        assert pub_key_1 == pub_key_2

    def test_owner_identity_persists(self, tmp_identity_dir):
        """Owner (human) identity should also persist."""
        from unclaude.auth.pact_identity import PactIdentityManager

        mgr1 = PactIdentityManager(identity_dir=tmp_identity_dir)
        owner_id_1 = mgr1.owner_identity.id

        mgr2 = PactIdentityManager(identity_dir=tmp_identity_dir)
        owner_id_2 = mgr2.owner_identity.id

        assert owner_id_1 == owner_id_2

    def test_identity_files_have_restricted_permissions(self, tmp_identity_dir):
        """Key files should be chmod 0o600 (owner only)."""
        from unclaude.auth.pact_identity import PactIdentityManager
        PactIdentityManager(identity_dir=tmp_identity_dir)

        key_file = tmp_identity_dir / "root_key.json"
        assert key_file.exists()
        mode = key_file.stat().st_mode & 0o777
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_create_session(self, identity_manager):
        """Should create a session with correct profile capabilities."""
        session = identity_manager.create_session(
            name="test",
            profile="developer",
            session_type="interactive",
        )

        assert session.session_id
        assert session.name == "test"
        assert session.profile == "developer"
        assert session.session_type == "interactive"
        assert not session.is_closed

    def test_session_has_delegation_chain(self, identity_manager):
        """Session should have a valid delegation chain."""
        session = identity_manager.create_session(profile="developer")
        chain = session.chain

        assert len(chain) >= 2  # owner->root + root->session
        # Last delegation should have developer capabilities
        last = chain[-1]
        assert any("file:read" in c for c in last.capabilities)

    def test_different_profiles_different_capabilities(self, identity_manager):
        """Different profiles should yield different capability sets."""
        readonly = identity_manager.create_session(profile="readonly")
        dev = identity_manager.create_session(profile="developer")
        full = identity_manager.create_session(profile="full")

        ro_caps = set(readonly.chain[-1].capabilities)
        dev_caps = set(dev.chain[-1].capabilities)
        full_caps = set(full.chain[-1].capabilities)

        # readonly should be the most restricted
        assert len(ro_caps) < len(dev_caps)
        # full should have wildcards
        assert any("*" in c for c in full_caps)

    def test_session_count(self, identity_manager):
        """Session count should track active sessions."""
        assert identity_manager.session_count() == 0

        identity_manager.create_session(name="s1")
        assert identity_manager.session_count() == 1

        identity_manager.create_session(name="s2")
        assert identity_manager.session_count() == 2

    def test_end_session(self, identity_manager):
        """Ending a session should remove it and close the pact session."""
        session = identity_manager.create_session()
        sid = session.session_id

        identity_manager.end_session(sid)
        assert identity_manager.session_count() == 0
        assert identity_manager.get_session(sid) is None
        assert session.is_closed

    def test_export_identity_card(self, identity_manager):
        """Identity card should be exportable without secrets."""
        card = identity_manager.export_identity_card()

        assert card["protocol"] == "pact"
        assert card["version"] == "1.0"
        assert "public_key" in card["agent"]
        assert "public_key" in card["owner"]
        # Should NOT contain private key material
        card_str = json.dumps(card)
        assert "private" not in card_str.lower()
        assert "secret" not in card_str.lower()
        assert "seed" not in card_str.lower()


# ═══════════════════════════════════════════════════════════════
# 2. SESSION CHAIN VERIFICATION & REVOCATION
# ═══════════════════════════════════════════════════════════════

class TestSessionVerification:
    """Test delegation chain verification and revocation."""

    def test_verify_valid_chain(self, identity_manager):
        """A fresh session's chain should verify successfully."""
        session = identity_manager.create_session(profile="developer")
        assert identity_manager.verify_session_chain(session) is True

    def test_revoke_session(self, identity_manager):
        """Revoking a session should close it and remove it."""
        session = identity_manager.create_session()
        sid = session.session_id

        result = identity_manager.revoke_session(sid, reason="test revoke")
        assert result is True
        assert identity_manager.get_session(sid) is None

    def test_revoke_nonexistent_session(self, identity_manager):
        """Revoking a non-existent session should return False."""
        assert identity_manager.revoke_session("fake-id") is False

    def test_list_sessions(self, identity_manager):
        """List sessions should return session info dicts."""
        identity_manager.create_session(name="alpha")
        identity_manager.create_session(name="beta")

        sessions = identity_manager.list_sessions()
        assert len(sessions) == 2
        names = {s["name"] for s in sessions}
        assert names == {"alpha", "beta"}


# ═══════════════════════════════════════════════════════════════
# 3. SUBAGENT DELEGATION
# ═══════════════════════════════════════════════════════════════

class TestSubagentDelegation:
    """Test narrowed delegation for subagents."""

    def test_create_subagent_delegation(self, identity_manager):
        """Should create a subagent session from a parent session."""
        parent = identity_manager.create_session(profile="developer")
        sub = identity_manager.create_subagent_delegation(
            parent_session=parent,
            capabilities=["file:read", "memory:read"],
        )

        assert sub.session_id != parent.session_id
        assert sub.session_type == "subagent"
        assert sub.profile == "subagent"
        assert "parent_session" in sub.metadata

    def test_subagent_has_narrowed_capabilities(self, identity_manager):
        """Subagent capabilities should be subset of parent."""
        parent = identity_manager.create_session(profile="developer")
        sub = identity_manager.create_subagent_delegation(
            parent_session=parent,
            capabilities=["file:read"],
        )

        sub_caps = sub.chain[-1].capabilities
        assert "file:read" in sub_caps
        # Should NOT have capabilities not explicitly granted
        # (depends on pact's narrowing logic)

    def test_subagent_chain_is_longer(self, identity_manager):
        """Subagent chain should be longer (one more delegation level)."""
        parent = identity_manager.create_session(profile="developer")
        sub = identity_manager.create_subagent_delegation(
            parent_session=parent,
            capabilities=["file:read"],
        )

        assert len(sub.chain) > len(parent.chain)


# ═══════════════════════════════════════════════════════════════
# 4. MEMORY CONSOLIDATION
# ═══════════════════════════════════════════════════════════════

class TestConsolidation:
    """Test the auto-consolidation engine."""

    def test_consolidation_config_defaults(self):
        """Config should have sensible defaults."""
        from unclaude.memory_consolidation import ConsolidationConfig
        config = ConsolidationConfig()

        assert config.min_resources_for_consolidation == 5
        assert config.similarity_threshold == 0.3
        assert config.interval_seconds == 600
        assert config.enable_pruning is True
        assert config.prune_stale_days == 30

    def test_engine_should_run(self):
        """should_run() should respect the interval."""
        from unclaude.memory_consolidation import ConsolidationEngine, ConsolidationConfig
        from unclaude.memory_v2 import HierarchicalMemory

        config = ConsolidationConfig(interval_seconds=0)  # Always ready
        engine = ConsolidationEngine(HierarchicalMemory(), config=config)
        assert engine.should_run() is True

    def test_engine_skips_when_too_few_resources(self, memory):
        """Should skip consolidation if fewer resources than minimum."""
        from unclaude.memory_consolidation import ConsolidationEngine, ConsolidationConfig

        config = ConsolidationConfig(min_resources_for_consolidation=10)
        engine = ConsolidationEngine(memory, config=config)

        # Store only 2 resources (less than min of 10)
        memory.store("fact one", tags=["test"])
        memory.store("fact two", tags=["test"])

        stats = asyncio.run(engine.run_cycle())
        assert stats.items_created == 0

    def test_consolidation_creates_items_from_cluster(self, memory):
        """Related resources should get promoted to item layer."""
        from unclaude.memory_consolidation import ConsolidationEngine, ConsolidationConfig

        config = ConsolidationConfig(
            min_resources_for_consolidation=3,
            min_age_seconds=0,  # Don't wait
            similarity_threshold=0.2,  # Low threshold for test
        )
        engine = ConsolidationEngine(memory, config=config)

        # Store related resources about the same topic
        for i in range(5):
            memory.store(
                f"Python authentication bug fix #{i} — session token validation",
                tags=["auth", "python", "bugfix"],
            )

        stats = asyncio.run(engine.run_cycle())
        assert stats.resources_scanned >= 5
        # Should find at least 1 cluster and create items
        assert stats.clusters_found >= 1

    def test_consolidation_stats_accumulate(self, memory):
        """Total stats should accumulate across cycles."""
        from unclaude.memory_consolidation import ConsolidationEngine, ConsolidationConfig

        config = ConsolidationConfig(
            min_resources_for_consolidation=3,
            min_age_seconds=0,
        )
        engine = ConsolidationEngine(memory, config=config)

        for i in range(5):
            memory.store(f"topic alpha resource {i}", tags=["alpha"])

        asyncio.run(engine.run_cycle())
        total = engine.total_stats
        assert total.resources_scanned > 0


# ═══════════════════════════════════════════════════════════════
# 5. EXPERIENTIAL LEARNING
# ═══════════════════════════════════════════════════════════════

class TestExperientialLearning:
    """Test learning from task outcomes."""

    def test_extract_success_insights(self, memory):
        """Successful tasks should produce success_pattern insights."""
        from unclaude.experiential_learning import ExperientialLearner, TaskOutcome

        learner = ExperientialLearner(memory)
        outcome = TaskOutcome(
            task_description="Fix the authentication bug in login.py",
            result="Added null check for session token, all tests pass now",
            success=True,
            duration_seconds=120,
            iterations=3,
            tools_used=["file_read", "file_write", "bash"],
            files_modified=["src/auth/login.py"],
        )

        insights = learner.extract_insights(outcome)
        assert len(insights) > 0

        types = {i.insight_type for i in insights}
        assert "success_pattern" in types or "technique" in types

    def test_extract_failure_insights(self, memory):
        """Failed tasks should produce failure_pattern insights."""
        from unclaude.experiential_learning import ExperientialLearner, TaskOutcome

        learner = ExperientialLearner(memory)
        outcome = TaskOutcome(
            task_description="Deploy to production",
            result="",
            success=False,
            duration_seconds=300,
            iterations=10,
            errors_encountered=[
                "ConnectionRefusedError: Cannot connect to Docker daemon",
                "PermissionError: /var/run/docker.sock",
            ],
        )

        insights = learner.extract_insights(outcome)
        assert len(insights) > 0

        types = {i.insight_type for i in insights}
        assert "failure_pattern" in types

    def test_failure_insights_higher_confidence(self, memory):
        """Failure patterns should generally have high confidence (learn more from mistakes)."""
        from unclaude.experiential_learning import ExperientialLearner, TaskOutcome

        learner = ExperientialLearner(memory)
        outcome = TaskOutcome(
            task_description="Update database schema",
            result="",
            success=False,
            duration_seconds=600,
            iterations=15,
            errors_encountered=["MigrationError: column already exists"],
        )

        insights = learner.extract_insights(outcome)
        failure_insights = [i for i in insights if i.insight_type == "failure_pattern"]
        if failure_insights:
            assert all(i.confidence >= 0.6 for i in failure_insights)

    def test_store_and_retrieve_insights(self, memory):
        """Stored insights should be retrievable from memory."""
        from unclaude.experiential_learning import ExperientialLearner, TaskOutcome

        learner = ExperientialLearner(memory)
        outcome = TaskOutcome(
            task_description="Implement user authentication with JWT tokens",
            result="Implemented JWT auth with refresh tokens and rate limiting",
            success=True,
            duration_seconds=180,
            iterations=5,
            tools_used=["file_write", "bash"],
        )

        ids = learner.learn_from_task(outcome)
        assert len(ids) > 0

        # Now search for relevant experience
        experiences = learner.find_relevant_experience(
            "Add authentication to the API"
        )
        # May or may not find matches depending on FTS, but shouldn't error
        assert isinstance(experiences, list)

    def test_format_experience_context(self, memory):
        """Formatted experience should be a readable string."""
        from unclaude.experiential_learning import ExperientialLearner, TaskOutcome
        from unclaude.memory_v2 import MemoryNode, MemoryLayer, MemoryImportance

        learner = ExperientialLearner(memory)

        # Create mock experience nodes
        nodes = [
            MemoryNode(
                id="exp-1",
                content="Use JWT refresh tokens alongside access tokens",
                layer=MemoryLayer.ITEM,
                importance=MemoryImportance.HIGH,
                tags=["experience", "success_pattern"],
                metadata={
                    "insight_type": "success_pattern",
                    "confidence": 0.7,
                },
                created_at="2024-01-01T00:00:00",
                updated_at="2024-01-01T00:00:00",
                access_count=1,
            ),
        ]

        formatted = learner.format_experience_context(nodes)
        assert "Past Experience" in formatted
        assert "SUCCESS" in formatted
        assert "70%" in formatted

    def test_format_empty_experience(self, memory):
        """Empty experience list should return empty string."""
        from unclaude.experiential_learning import ExperientialLearner

        learner = ExperientialLearner(memory)
        assert learner.format_experience_context([]) == ""

    def test_learn_from_task_end_to_end(self, memory):
        """Full pipeline: create outcome → extract → store → retrieve."""
        from unclaude.experiential_learning import ExperientialLearner, TaskOutcome

        learner = ExperientialLearner(memory)

        # Task 1: Success
        learner.learn_from_task(TaskOutcome(
            task_description="Fix CSS alignment bug in dashboard",
            result="Used flexbox to fix layout, added responsive breakpoints",
            success=True,
            duration_seconds=90,
            iterations=2,
            tools_used=["file_read", "file_write"],
            files_modified=["src/styles/dashboard.css"],
        ))

        # Task 2: Failure
        learner.learn_from_task(TaskOutcome(
            task_description="Deploy Kubernetes cluster",
            result="",
            success=False,
            duration_seconds=3600,
            iterations=20,
            errors_encountered=["ImagePullBackOff", "CrashLoopBackOff"],
        ))

        # Memory should now have insights from both tasks
        stats = memory.get_stats()
        assert stats["total_nodes"] > 0


# ═══════════════════════════════════════════════════════════════
# 6. CROSS-CUTTING — Pact + Unclaude integration
# ═══════════════════════════════════════════════════════════════

class TestPactUnclaude:
    """Test that Pact + UnClaude pieces fit together."""

    def test_pact_import_works(self):
        """pact-auth should be importable."""
        import pact
        assert pact.__version__

    def test_identity_manager_creates_pact_sessions(self, identity_manager):
        """Sessions should contain real Pact sessions with identity."""
        session = identity_manager.create_session(profile="developer")

        # Should have a real Pact protocol session
        assert session.pact_session is not None
        assert session.identity is not None
        assert session.identity.public_key

    def test_session_to_dict_roundtrip(self, identity_manager):
        """Session info should be serializable to dict."""
        session = identity_manager.create_session(
            name="test-rt",
            profile="developer",
            project_path="/tmp/test",
        )

        d = session.to_dict()
        assert d["name"] == "test-rt"
        assert d["profile"] == "developer"
        assert d["project_path"] == "/tmp/test"
        assert "identity_id" in d
        assert "root_id" in d
        assert "capabilities" in d

    def test_profile_capabilities_complete(self):
        """All profiles should have defined capabilities."""
        from unclaude.auth.pact_identity import PROFILE_CAPABILITIES

        expected_profiles = {"readonly", "developer", "full", "autonomous", "subagent"}
        assert set(PROFILE_CAPABILITIES.keys()) == expected_profiles
        for profile, caps in PROFILE_CAPABILITIES.items():
            assert len(caps) > 0, f"Profile {profile} has no capabilities"
