"""Auto-consolidation engine for hierarchical memory.

Solves the gap: memory_v2 has consolidate() and categorize() methods
but they never run automatically. This engine runs during idle periods
(called by the daemon) and performs the full memory lifecycle:

1. SCAN    — Find recent Resource-layer nodes not yet consolidated
2. CLUSTER — Group related resources by topic/project similarity
3. PROMOTE — Call consolidate() to merge clusters into Item-layer nodes
4. CATEGORIZE — Group Items into Category-layer nodes
5. PRUNE   — Remove stale nodes past their TTL

The consolidation mimics biological memory: recent events (resources)
are episodic, frequently-accessed patterns get promoted to semantic
memory (items), and overarching themes become categories.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unclaude.memory_v2 import (
    HierarchicalMemory,
    MemoryLayer,
    MemoryNode,
    MemoryImportance,
)

logger = logging.getLogger(__name__)


@dataclass
class ConsolidationStats:
    """Stats from a consolidation run."""
    resources_scanned: int = 0
    clusters_found: int = 0
    items_created: int = 0
    categories_created: int = 0
    nodes_pruned: int = 0
    duration_seconds: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resources_scanned": self.resources_scanned,
            "clusters_found": self.clusters_found,
            "items_created": self.items_created,
            "categories_created": self.categories_created,
            "nodes_pruned": self.nodes_pruned,
            "duration_seconds": round(self.duration_seconds, 2),
            "timestamp": self.timestamp,
        }


@dataclass
class ConsolidationConfig:
    """Configuration for the consolidation engine."""
    # Minimum resources before attempting consolidation
    min_resources_for_consolidation: int = 5
    # How old a resource must be before consolidation (seconds)
    min_age_seconds: float = 300  # 5 minutes
    # Minimum similarity score to cluster resources together
    similarity_threshold: float = 0.3
    # Maximum resources to process per run
    batch_size: int = 50
    # How often to run consolidation (seconds)
    interval_seconds: float = 600  # 10 minutes
    # Enable pruning during consolidation
    enable_pruning: bool = True
    # Prune nodes older than this (days)
    prune_stale_days: int = 30


class ConsolidationEngine:
    """Automatic memory consolidation engine.

    Usage:
        memory = HierarchicalMemory()
        engine = ConsolidationEngine(memory)

        # Run once (called from daemon idle loop)
        stats = await engine.run_cycle()

        # Run continuously (background task)
        await engine.run_forever()
    """

    def __init__(
        self,
        memory: HierarchicalMemory,
        config: ConsolidationConfig | None = None,
    ):
        self.memory = memory
        self.config = config or ConsolidationConfig()
        self._running = False
        self._last_run: float = 0
        self._total_stats = ConsolidationStats()

    async def run_cycle(self) -> ConsolidationStats:
        """Run a single consolidation cycle.

        Returns stats about what was consolidated.
        """
        start = time.time()
        stats = ConsolidationStats()

        try:
            # Step 1: Scan recent resources
            resources = self._scan_unconsolidated_resources()
            stats.resources_scanned = len(resources)

            if len(resources) < self.config.min_resources_for_consolidation:
                stats.duration_seconds = time.time() - start
                return stats

            # Step 2: Cluster by similarity
            clusters = self._cluster_resources(resources)
            stats.clusters_found = len(clusters)

            # Step 3: Promote clusters to items
            for cluster in clusters:
                if len(cluster) >= 2:
                    item = self._promote_cluster(cluster)
                    if item:
                        stats.items_created += 1

            # Step 4: Categorize items
            categories_created = self._auto_categorize()
            stats.categories_created = categories_created

            # Step 5: Prune stale nodes
            if self.config.enable_pruning:
                pruned = self.memory.prune_stale(
                    max_age_days=self.config.prune_stale_days)
                stats.nodes_pruned = pruned

        except Exception as e:
            logger.error(f"Consolidation cycle error: {e}")

        stats.duration_seconds = time.time() - start
        self._last_run = time.time()

        # Accumulate totals
        self._total_stats.resources_scanned += stats.resources_scanned
        self._total_stats.clusters_found += stats.clusters_found
        self._total_stats.items_created += stats.items_created
        self._total_stats.categories_created += stats.categories_created
        self._total_stats.nodes_pruned += stats.nodes_pruned

        logger.info(
            f"Consolidation: scanned={stats.resources_scanned} "
            f"clusters={stats.clusters_found} items={stats.items_created} "
            f"pruned={stats.nodes_pruned} ({stats.duration_seconds:.1f}s)"
        )

        return stats

    async def run_forever(self, shutdown_event: asyncio.Event | None = None) -> None:
        """Run consolidation cycles forever (or until shutdown)."""
        self._running = True
        while self._running:
            if shutdown_event and shutdown_event.is_set():
                break

            # Wait for the interval
            elapsed = time.time() - self._last_run
            if elapsed < self.config.interval_seconds:
                wait_time = self.config.interval_seconds - elapsed
                try:
                    if shutdown_event:
                        await asyncio.wait_for(
                            shutdown_event.wait(), timeout=wait_time
                        )
                        break
                    else:
                        await asyncio.sleep(wait_time)
                except asyncio.TimeoutError:
                    pass

            await self.run_cycle()

        self._running = False

    def stop(self) -> None:
        """Signal the engine to stop."""
        self._running = False

    def should_run(self) -> bool:
        """Check if enough time has passed since the last run."""
        return (time.time() - self._last_run) >= self.config.interval_seconds

    @property
    def total_stats(self) -> ConsolidationStats:
        return self._total_stats

    # ── Internal methods ──────────────────────────────────────────

    def _scan_unconsolidated_resources(self) -> list[MemoryNode]:
        """Find Resource-layer nodes that haven't been consolidated yet."""
        cutoff = time.time() - self.config.min_age_seconds

        # Use direct DB query since FTS doesn't support empty queries
        import sqlite3
        conn = sqlite3.connect(self.memory.db_path)
        c = conn.cursor()
        c.execute(
            """
            SELECT * FROM memory_nodes
            WHERE layer = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (MemoryLayer.RESOURCE.value, self.config.batch_size),
        )
        from unclaude.memory_v2 import HierarchicalMemory
        results = [HierarchicalMemory._row_to_node(row) for row in c.fetchall()]
        conn.close()

        # Filter to those old enough and not already consolidated
        eligible = []
        for node in results:
            # created_at is ISO string, convert for comparison
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(node.created_at)
                ts = dt.timestamp()
            except (ValueError, TypeError):
                ts = 0

            if ts <= cutoff and not self._is_consolidated(node):
                eligible.append(node)

        return eligible

    def _is_consolidated(self, node: MemoryNode) -> bool:
        """Check if a resource node is already part of an Item."""
        # A consolidated node has been referenced by a higher-layer node
        # We check by looking for references in the Item layer
        refs = node.metadata.get("_consolidated", False)
        return bool(refs)

    def _cluster_resources(self, resources: list[MemoryNode]) -> list[list[MemoryNode]]:
        """Cluster resources by content similarity.

        Uses a simple keyword-overlap approach (no embeddings needed).
        Resources about the same topic/file/project cluster together.
        """
        if not resources:
            return []

        clusters: list[list[MemoryNode]] = []
        assigned = set()

        for i, node_a in enumerate(resources):
            if i in assigned:
                continue

            cluster = [node_a]
            assigned.add(i)
            tokens_a = self._tokenize(node_a)

            for j, node_b in enumerate(resources):
                if j in assigned or j <= i:
                    continue

                tokens_b = self._tokenize(node_b)
                similarity = self._jaccard_similarity(tokens_a, tokens_b)

                if similarity >= self.config.similarity_threshold:
                    cluster.append(node_b)
                    assigned.add(j)

            clusters.append(cluster)

        return clusters

    def _promote_cluster(self, cluster: list[MemoryNode]) -> MemoryNode | None:
        """Promote a cluster of Resources into a single Item node."""
        if not cluster:
            return None

        # Merge content: take the most important node's content as base,
        # append unique details from others
        cluster.sort(key=lambda n: n.importance_weight, reverse=True)
        primary = cluster[0]

        # Build consolidated content
        contents = [primary.content]
        for node in cluster[1:]:
            # Only add if it brings new information
            if node.content not in primary.content:
                contents.append(f"- {node.content[:200]}")

        merged_content = contents[0]
        if len(contents) > 1:
            merged_content += "\n\nRelated:\n" + "\n".join(contents[1:5])

        # Average importance, boosted slightly for consolidation
        avg_importance = sum(
            n.importance_weight for n in cluster) / len(cluster)
        boosted = min(1.0, avg_importance * 1.2)

        # Determine importance level
        if boosted >= 0.8:
            importance = MemoryImportance.CRITICAL
        elif boosted >= 0.5:
            importance = MemoryImportance.HIGH
        elif boosted >= 0.3:
            importance = MemoryImportance.MEDIUM
        else:
            importance = MemoryImportance.LOW

        # Store as Item
        try:
            item_id = self.memory.store(
                content=merged_content,
                layer=MemoryLayer.ITEM,
                importance=importance,
                tags=self._merge_tags(cluster),
                metadata={
                    "source": "consolidation",
                    "source_count": len(cluster),
                    "source_ids": [n.node_id for n in cluster[:10]],
                },
            )

            # Mark source nodes as consolidated
            for node in cluster:
                node.metadata["_consolidated"] = True
                # Add cross-reference
                try:
                    self.memory.add_reference(item_id, node.node_id)
                except Exception:
                    pass

            # Return the created item
            results = self.memory.search(
                query=merged_content[:50], layer=MemoryLayer.ITEM, limit=1)
            return results[0] if results else None

        except Exception as e:
            logger.error(f"Failed to promote cluster: {e}")
            return None

    def _auto_categorize(self) -> int:
        """Group uncategorized Items into Categories."""
        items = self.memory.search(
            query="",
            layer=MemoryLayer.ITEM,
            limit=100,
        )

        # Group items by their primary tag
        tag_groups: dict[str, list[MemoryNode]] = {}
        for item in items:
            primary_tag = item.tags[0] if item.tags else "general"
            if primary_tag not in tag_groups:
                tag_groups[primary_tag] = []
            tag_groups[primary_tag].append(item)

        categories_created = 0

        for tag, group in tag_groups.items():
            if len(group) >= 3:  # Need at least 3 items to form a category
                # Check if category already exists
                existing = self.memory.search(
                    query=tag,
                    layer=MemoryLayer.CATEGORY,
                    limit=1,
                )
                if not existing:
                    try:
                        cat_content = (
                            f"Category: {tag}\n"
                            f"Contains {len(group)} related items about {tag}."
                        )
                        self.memory.store(
                            content=cat_content,
                            layer=MemoryLayer.CATEGORY,
                            importance=MemoryImportance.HIGH,
                            tags=[tag],
                            metadata={
                                "source": "auto_categorize",
                                "item_count": len(group),
                            },
                        )
                        categories_created += 1
                    except Exception as e:
                        logger.error(f"Failed to create category '{tag}': {e}")

        return categories_created

    def _tokenize(self, node: MemoryNode) -> set[str]:
        """Extract keyword tokens from a node for similarity comparison."""
        text = f"{node.content} {' '.join(node.tags)}".lower()
        # Simple word tokenization, skip very short words
        words = set()
        for word in text.split():
            # Strip punctuation
            clean = word.strip(".,;:!?()[]{}\"'`")
            if len(clean) >= 3:
                words.add(clean)
        return words

    def _jaccard_similarity(self, a: set[str], b: set[str]) -> float:
        """Jaccard similarity between two token sets."""
        if not a or not b:
            return 0.0
        intersection = len(a & b)
        union = len(a | b)
        return intersection / union if union > 0 else 0.0

    def _merge_tags(self, cluster: list[MemoryNode]) -> list[str]:
        """Merge tags from cluster nodes, keeping the most common."""
        from collections import Counter
        tag_counts: Counter[str] = Counter()
        for node in cluster:
            tag_counts.update(node.tags)
        return [tag for tag, _ in tag_counts.most_common(5)]
