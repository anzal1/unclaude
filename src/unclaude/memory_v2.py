"""Hierarchical memory system.

Evolves the existing flat SQLite memory into a 3-layer hierarchical
system inspired by memU:

Layer 1: Resources  - Raw memories (files read, errors seen, user prefs)
Layer 2: Items      - Consolidated knowledge (grouped resources)
Layer 3: Categories - High-level topics (project structure, conventions)

Features:
- Time-decay salience scoring (recent memories rank higher)
- Cross-referencing between related memories
- Keyword-based + semantic search (when embeddings available)
- Memory-as-filesystem metaphor for LLM tool access
- Dual retrieval: direct keyword search + LLM-guided search
"""

import json
import math
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class MemoryLayer(str, Enum):
    """The three memory layers."""
    RESOURCE = "resource"    # Raw observations
    ITEM = "item"            # Consolidated knowledge
    CATEGORY = "category"    # High-level topics


class MemoryImportance(str, Enum):
    """Importance levels for memories."""
    CRITICAL = "critical"    # User preferences, credentials info
    HIGH = "high"            # Architecture decisions, conventions
    MEDIUM = "medium"        # Code patterns, file locations
    LOW = "low"              # Transient observations


@dataclass
class MemoryNode:
    """A node in the hierarchical memory graph."""
    id: str
    layer: MemoryLayer
    content: str
    importance: MemoryImportance = MemoryImportance.MEDIUM
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_id: str | None = None  # Item → Category link
    project_path: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = 0.0

    @property
    def salience(self) -> float:
        """Calculate salience score with time decay.

        Factors:
        - Importance weight (critical=1.0, high=0.75, medium=0.5, low=0.25)
        - Recency decay (half-life of 7 days)
        - Access frequency bonus
        """
        importance_weights = {
            MemoryImportance.CRITICAL: 1.0,
            MemoryImportance.HIGH: 0.75,
            MemoryImportance.MEDIUM: 0.5,
            MemoryImportance.LOW: 0.25,
        }

        base = importance_weights.get(self.importance, 0.5)

        # Time decay: half-life of 7 days
        age_days = (time.time() - self.updated_at) / 86400
        decay = math.exp(-0.099 * age_days)  # ln(2)/7 ≈ 0.099

        # Access frequency bonus (log scale, capped)
        freq_bonus = min(0.3, math.log1p(self.access_count) * 0.1)

        return base * decay + freq_bonus


class HierarchicalMemory:
    """3-layer hierarchical memory with salience scoring.

    This wraps and extends the existing MemoryStore, adding:
    - Hierarchical organization (resource → item → category)
    - Salience-based retrieval
    - Cross-referencing
    - Tag-based search
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (Path.home() / ".unclaude" / "memory_v2.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize hierarchical memory schema."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Main nodes table
        c.execute("""
            CREATE TABLE IF NOT EXISTS memory_nodes (
                id TEXT PRIMARY KEY,
                layer TEXT NOT NULL,
                content TEXT NOT NULL,
                importance TEXT DEFAULT 'medium',
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                parent_id TEXT,
                project_path TEXT,
                created_at REAL,
                updated_at REAL,
                access_count INTEGER DEFAULT 0,
                last_accessed REAL DEFAULT 0,
                FOREIGN KEY (parent_id) REFERENCES memory_nodes(id)
            )
        """)

        # Cross-references table
        c.execute("""
            CREATE TABLE IF NOT EXISTS memory_refs (
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                ref_type TEXT DEFAULT 'related',
                strength REAL DEFAULT 1.0,
                created_at REAL,
                PRIMARY KEY (source_id, target_id),
                FOREIGN KEY (source_id) REFERENCES memory_nodes(id),
                FOREIGN KEY (target_id) REFERENCES memory_nodes(id)
            )
        """)

        # Full-text search index
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(content, tags, id UNINDEXED)
        """)

        # Indexes
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_nodes_layer ON memory_nodes(layer)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_nodes_project ON memory_nodes(project_path)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_nodes_parent ON memory_nodes(parent_id)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_nodes_importance ON memory_nodes(importance)")

        conn.commit()
        conn.close()

    def store(
        self,
        content: str,
        layer: MemoryLayer = MemoryLayer.RESOURCE,
        importance: MemoryImportance = MemoryImportance.MEDIUM,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        parent_id: str | None = None,
        project_path: str | None = None,
    ) -> str:
        """Store a memory node.

        Args:
            content: The memory content.
            layer: Which layer (resource/item/category).
            importance: How important this memory is.
            tags: Searchable tags.
            metadata: Additional metadata.
            parent_id: Parent node ID (for hierarchy).
            project_path: Associated project.

        Returns:
            The memory node ID.
        """
        node_id = str(uuid.uuid4())[:12]
        now = time.time()
        tags = tags or []

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            INSERT INTO memory_nodes 
            (id, layer, content, importance, tags, metadata, parent_id, 
             project_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            node_id, layer.value, content, importance.value,
            json.dumps(tags), json.dumps(metadata or {}),
            parent_id, project_path, now, now,
        ))

        # Update FTS index
        c.execute(
            "INSERT INTO memory_fts (id, content, tags) VALUES (?, ?, ?)",
            (node_id, content, " ".join(tags)),
        )

        conn.commit()
        conn.close()
        return node_id

    def search(
        self,
        query: str,
        layer: MemoryLayer | None = None,
        project_path: str | None = None,
        importance_min: MemoryImportance | None = None,
        limit: int = 10,
        use_fts: bool = True,
    ) -> list[MemoryNode]:
        """Search memories with salience-based ranking.

        Uses FTS5 for full-text search, then re-ranks by salience.

        Args:
            query: Search query.
            layer: Filter by layer.
            project_path: Filter by project.
            importance_min: Minimum importance level.
            limit: Max results.
            use_fts: Whether to use FTS (else falls back to LIKE).

        Returns:
            List of MemoryNodes ranked by salience.
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        if use_fts:
            # FTS5 search with BM25 scoring
            sql = """
                SELECT n.*, fts.rank
                FROM memory_fts fts
                JOIN memory_nodes n ON n.id = fts.id
                WHERE memory_fts MATCH ?
            """
            params: list[Any] = [self._fts_query(query)]
        else:
            # Fallback to LIKE search
            words = [w for w in query.split() if len(w) > 2]
            if not words:
                words = [query]
            like_clauses = " OR ".join(["n.content LIKE ?" for _ in words])
            sql = f"""
                SELECT n.*, 0 as rank
                FROM memory_nodes n
                WHERE ({like_clauses})
            """
            params = [f"%{w}%" for w in words]

        if layer:
            sql += " AND n.layer = ?"
            params.append(layer.value)

        if project_path:
            sql += " AND (n.project_path = ? OR n.project_path IS NULL)"
            params.append(project_path)

        if importance_min:
            importance_order = {
                MemoryImportance.LOW: 0,
                MemoryImportance.MEDIUM: 1,
                MemoryImportance.HIGH: 2,
                MemoryImportance.CRITICAL: 3,
            }
            min_level = importance_order.get(importance_min, 0)
            valid_importances = [
                imp.value for imp, level in importance_order.items()
                if level >= min_level
            ]
            placeholders = ",".join("?" * len(valid_importances))
            sql += f" AND n.importance IN ({placeholders})"
            params.extend(valid_importances)

        sql += f" LIMIT {limit * 3}"  # Fetch extra for re-ranking
        c.execute(sql, params)

        nodes = []
        for row in c.fetchall():
            node = self._row_to_node(row)
            nodes.append(node)

            # Update access stats
            c.execute(
                "UPDATE memory_nodes SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                (time.time(), node.id),
            )

        conn.commit()
        conn.close()

        # Re-rank by salience
        nodes.sort(key=lambda n: n.salience, reverse=True)
        return nodes[:limit]

    def get_hierarchy(
        self,
        node_id: str,
    ) -> dict[str, Any]:
        """Get a node and its full hierarchy (up to category, down to resources).

        Returns:
            Dict with 'node', 'parent', 'children' keys.
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Get the node
        c.execute("SELECT * FROM memory_nodes WHERE id = ?", (node_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return {}

        node = self._row_to_node(row)

        # Get parent
        parent = None
        if node.parent_id:
            c.execute("SELECT * FROM memory_nodes WHERE id = ?",
                      (node.parent_id,))
            parent_row = c.fetchone()
            if parent_row:
                parent = self._row_to_node(parent_row)

        # Get children
        c.execute("SELECT * FROM memory_nodes WHERE parent_id = ?", (node_id,))
        children = [self._row_to_node(r) for r in c.fetchall()]

        # Get cross-references
        c.execute("""
            SELECT m.*, r.ref_type, r.strength
            FROM memory_refs r
            JOIN memory_nodes m ON m.id = r.target_id
            WHERE r.source_id = ?
        """, (node_id,))
        refs = [self._row_to_node(r) for r in c.fetchall()]

        conn.close()

        return {
            "node": node,
            "parent": parent,
            "children": children,
            "references": refs,
        }

    def consolidate(
        self,
        resource_ids: list[str],
        summary: str,
        tags: list[str] | None = None,
        project_path: str | None = None,
    ) -> str:
        """Consolidate multiple resources into an item.

        This promotes raw observations into consolidated knowledge.

        Args:
            resource_ids: List of resource node IDs to consolidate.
            summary: The consolidated summary.
            tags: Tags for the item.
            project_path: Associated project.

        Returns:
            The new item node ID.
        """
        item_id = self.store(
            content=summary,
            layer=MemoryLayer.ITEM,
            importance=MemoryImportance.HIGH,
            tags=tags,
            metadata={"source_resources": resource_ids},
            project_path=project_path,
        )

        # Link resources to item
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        for rid in resource_ids:
            c.execute(
                "UPDATE memory_nodes SET parent_id = ? WHERE id = ?",
                (item_id, rid),
            )
        conn.commit()
        conn.close()

        return item_id

    def categorize(
        self,
        item_ids: list[str],
        category_name: str,
        description: str,
        project_path: str | None = None,
    ) -> str:
        """Group items under a category.

        Args:
            item_ids: List of item IDs to categorize.
            category_name: Category name.
            description: Category description.
            project_path: Associated project.

        Returns:
            The category node ID.
        """
        cat_id = self.store(
            content=description,
            layer=MemoryLayer.CATEGORY,
            importance=MemoryImportance.HIGH,
            tags=[category_name],
            metadata={"category_name": category_name},
            project_path=project_path,
        )

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        for iid in item_ids:
            c.execute(
                "UPDATE memory_nodes SET parent_id = ? WHERE id = ?",
                (cat_id, iid),
            )
        conn.commit()
        conn.close()

        return cat_id

    def add_reference(
        self,
        source_id: str,
        target_id: str,
        ref_type: str = "related",
        strength: float = 1.0,
    ) -> None:
        """Add a cross-reference between two memories."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO memory_refs
            (source_id, target_id, ref_type, strength, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (source_id, target_id, ref_type, strength, time.time()))
        conn.commit()
        conn.close()

    def list_categories(
        self,
        project_path: str | None = None,
    ) -> list[MemoryNode]:
        """List all categories, optionally filtered by project."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        if project_path:
            c.execute(
                "SELECT * FROM memory_nodes WHERE layer = 'category' AND (project_path = ? OR project_path IS NULL)",
                (project_path,),
            )
        else:
            c.execute("SELECT * FROM memory_nodes WHERE layer = 'category'")

        nodes = [self._row_to_node(r) for r in c.fetchall()]
        conn.close()
        return nodes

    def prune_stale(
        self,
        max_age_days: float = 90,
        min_importance: MemoryImportance = MemoryImportance.MEDIUM,
    ) -> int:
        """Remove stale low-importance memories.

        Only prunes RESOURCE layer nodes that are:
        - Older than max_age_days
        - Below min_importance
        - Not accessed recently

        Returns:
            Number of pruned nodes.
        """
        cutoff = time.time() - (max_age_days * 86400)
        importance_order = {
            MemoryImportance.LOW: 0,
            MemoryImportance.MEDIUM: 1,
            MemoryImportance.HIGH: 2,
            MemoryImportance.CRITICAL: 3,
        }
        min_level = importance_order.get(min_importance, 1)
        prune_importances = [
            imp.value for imp, level in importance_order.items()
            if level < min_level
        ]

        if not prune_importances:
            return 0

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        placeholders = ",".join("?" * len(prune_importances))
        c.execute(f"""
            SELECT id FROM memory_nodes 
            WHERE layer = 'resource' 
            AND updated_at < ? 
            AND importance IN ({placeholders})
            AND parent_id IS NULL
        """, [cutoff] + prune_importances)

        ids = [r[0] for r in c.fetchall()]
        for nid in ids:
            c.execute("DELETE FROM memory_fts WHERE id = ?", (nid,))
            c.execute(
                "DELETE FROM memory_refs WHERE source_id = ? OR target_id = ?", (nid, nid))
            c.execute("DELETE FROM memory_nodes WHERE id = ?", (nid,))

        conn.commit()
        conn.close()
        return len(ids)

    def migrate_from_v1(self, v1_db_path: Path) -> int:
        """Migrate memories from the old flat MemoryStore.

        Imports all memories as RESOURCE layer nodes with MEDIUM importance.

        Returns:
            Number of migrated memories.
        """
        if not v1_db_path.exists():
            return 0

        v1_conn = sqlite3.connect(v1_db_path)
        v1_c = v1_conn.cursor()

        try:
            v1_c.execute(
                "SELECT id, memory_type, content, metadata, project_path, created_at FROM memories"
            )
        except sqlite3.OperationalError:
            v1_conn.close()
            return 0

        count = 0
        for row in v1_c.fetchall():
            old_id, mem_type, content, metadata_str, project, created = row

            # Map old types to importance
            importance = {
                "core": MemoryImportance.CRITICAL,
                "recall": MemoryImportance.MEDIUM,
                "archival": MemoryImportance.LOW,
            }.get(mem_type, MemoryImportance.MEDIUM)

            metadata = json.loads(metadata_str) if metadata_str else {}
            tags = metadata.get("tags", [])

            self.store(
                content=content,
                layer=MemoryLayer.RESOURCE,
                importance=importance,
                tags=tags,
                metadata={"migrated_from": old_id,
                          "old_type": mem_type, **metadata},
                project_path=project,
            )
            count += 1

        v1_conn.close()
        return count

    def get_stats(self) -> dict[str, Any]:
        """Get memory system statistics."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("SELECT layer, COUNT(*) FROM memory_nodes GROUP BY layer")
        layer_counts = dict(c.fetchall())

        c.execute("SELECT COUNT(*) FROM memory_refs")
        ref_count = c.fetchone()[0]

        c.execute(
            "SELECT COUNT(DISTINCT project_path) FROM memory_nodes WHERE project_path IS NOT NULL")
        project_count = c.fetchone()[0]

        conn.close()

        return {
            "total_nodes": sum(layer_counts.values()),
            "resources": layer_counts.get("resource", 0),
            "items": layer_counts.get("item", 0),
            "categories": layer_counts.get("category", 0),
            "cross_references": ref_count,
            "projects": project_count,
        }

    @staticmethod
    def _fts_query(query: str) -> str:
        """Convert a natural language query to FTS5 query syntax."""
        import re
        # Strip non-alphanumeric characters (FTS5 special chars like commas break syntax)
        cleaned = re.sub(r'[^\w\s]', ' ', query)
        # FTS5 reserved keywords that must be excluded or they break syntax
        fts5_reserved = {'AND', 'OR', 'NOT', 'NEAR'}
        # Split into words, filter short ones and reserved words, join with OR
        words = [w.strip() for w in cleaned.split()
                 if len(w.strip()) > 2 and w.strip().upper() not in fts5_reserved]
        if not words:
            # Fallback: quote the whole cleaned query to treat as literal
            safe = re.sub(r'[^\w\s]', '', query)
            return f'"{safe}"' if safe.strip() else '"query"'
        # FTS5 implicit AND is too strict, use OR
        return " OR ".join(words)

    @staticmethod
    def _row_to_node(row: tuple) -> MemoryNode:
        """Convert a database row to a MemoryNode."""
        return MemoryNode(
            id=row[0],
            layer=MemoryLayer(row[1]),
            content=row[2],
            importance=MemoryImportance(row[3]),
            tags=json.loads(row[4]) if row[4] else [],
            metadata=json.loads(row[5]) if row[5] else {},
            parent_id=row[6],
            project_path=row[7],
            created_at=row[8] or 0,
            updated_at=row[9] or 0,
            access_count=row[10] or 0,
            last_accessed=row[11] or 0,
        )
