from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    Distance,
    Filter,
    FieldCondition,
    MatchValue,
    PointStruct,
    ScrollRequest,
    UpdateStatus,
)

from aos_context.ledger import utc_iso
from aos_context.memory import CommitResult, MemoryStore, ProposeResult
from aos_context.validation import assert_valid, validate_instance


class QdrantMemoryStore(MemoryStore):
    """Production-grade Memory Backend using Qdrant vector database.

    Supports propose/commit workflow with vector similarity search.
    Uses embedding function to convert text to vectors for semantic search.
    """

    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        embedding_fn: Callable[[str], List[float]],
    ) -> None:
        """Initialize Qdrant memory store.

        Args:
            client: QdrantClient instance (can be in-memory or remote)
            collection_name: Name of the Qdrant collection
            embedding_fn: Function that converts text to embedding vector
        """
        self.client = client
        self.collection_name = collection_name
        self.embedding_fn = embedding_fn

    def propose(
        self, mcrs: List[Dict[str, Any]], *, scope_filters: Dict[str, Any]
    ) -> ProposeResult:
        """Stage memory change requests (MCRs) for later commit.

        Args:
            mcrs: List of Memory Change Requests
            scope_filters: Scope filters to attach to staged items

        Returns:
            ProposeResult with batch_id if successful
        """
        # Validate MCR schema
        for m in mcrs:
            res = validate_instance("mcr.v2.1.schema.json", m)
            if not res.ok:
                return ProposeResult(ok=False, error=f"mcr schema: {res.error}")

        batch_id = f"batch_{uuid.uuid4().hex}"

        # Prepare points for Qdrant
        points: List[PointStruct] = []
        for m in mcrs:
            # Generate embedding from content
            content = str(m.get("content", ""))
            vector = self.embedding_fn(content)

            # Generate unique point ID (Qdrant requires UUID or int)
            # Use UUID for point_id, store memory_id in payload
            point_id = uuid.uuid4()
            memory_id = m.get("memory_id") or f"mem_{uuid.uuid4().hex}"

            # Create payload with staged status
            payload: Dict[str, Any] = {
                "status": "staged",
                "batch_id": batch_id,
                "memory_id": memory_id,  # Store original memory_id in payload
                "content": content,
                "type": m.get("type", "fact"),
                "scope": m.get("scope", "global"),
                "user_id": m.get("user_id"),
                "project_id": m.get("project_id"),
                "confidence": float(m.get("confidence", 0.8)),
                "op": m.get("op", "add"),
                "supersedes": m.get("supersedes", []),
                "source_refs": m.get("source_refs", []),
                "created_at": m.get("created_at") or utc_iso(),
                "_scope_filters": dict(scope_filters),
            }

            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        # Insert points into Qdrant
        try:
            self.client.upsert(
                collection_name=self.collection_name, wait=True, points=points
            )
        except Exception as e:
            return ProposeResult(ok=False, error=f"Qdrant upsert failed: {e}")

        return ProposeResult(ok=True, batch_id=batch_id)

    def commit(self, batch_id: str) -> CommitResult:
        """Commit staged memory items to active status.

        Also handles supersede logic to deprecate old memories.

        Args:
            batch_id: Batch ID from propose() call

        Returns:
            CommitResult with list of committed memory IDs
        """
        # Scroll to find all items with this batch_id
        filter_condition = Filter(
            must=[
                FieldCondition(
                    key="batch_id", match=MatchValue(value=batch_id)
                ),
                FieldCondition(
                    key="status", match=MatchValue(value="staged")
                ),
            ]
        )

        try:
            # Scroll through all matching points
            # We need vectors=False for scroll, but we'll re-embed during update
            scroll_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=filter_condition,
                limit=10000,  # Large limit to get all items
                with_payload=True,
                with_vectors=False,  # Don't need vectors, we'll re-embed
            )

            points_to_update: List[PointStruct] = []
            committed_ids: List[str] = []

            # scroll_result is (points, next_page_offset)
            points_list = scroll_result[0]
            for point in points_list:
                point_id = point.id
                payload = point.payload or {}
                # Update payload to active status
                new_payload = dict(payload)
                new_payload["status"] = "active"
                new_payload["updated_at"] = utc_iso()
                # Remove batch_id from payload (no longer needed)
                if "batch_id" in new_payload:
                    del new_payload["batch_id"]

                # Get memory_id (use point_id if not in payload)
                memory_id = new_payload.get("memory_id") or str(point_id)
                committed_ids.append(memory_id)

                # Get embedding for this point (need to re-embed)
                content = str(new_payload.get("content", ""))
                vector = self.embedding_fn(content)

                points_to_update.append(
                    PointStruct(id=point_id, vector=vector, payload=new_payload)
                )

                # Handle supersede logic
                supersedes = new_payload.get("supersedes", [])
                if supersedes:
                    # Find and deprecate old memories
                    for old_id in supersedes:
                        # Try to find point by memory_id in payload
                        old_filter = Filter(
                            must=[
                                FieldCondition(
                                    key="memory_id",
                                    match=MatchValue(value=old_id),
                                ),
                                FieldCondition(
                                    key="status",
                                    match=MatchValue(value="active"),
                                ),
                            ]
                        )
                        old_scroll = self.client.scroll(
                            collection_name=self.collection_name,
                            scroll_filter=old_filter,
                            limit=1,
                            with_payload=True,
                            with_vectors=False,
                        )

                        if old_scroll[0]:
                            old_point = old_scroll[0][0]
                            old_point_id = old_point.id
                            old_payload = old_point.payload or {}
                            # Update old memory to deprecated
                            deprecated_payload = dict(old_payload)
                            deprecated_payload["status"] = "deprecated"
                            deprecated_payload["updated_at"] = utc_iso()

                            # Re-embed old content
                            old_content = str(deprecated_payload.get("content", ""))
                            old_vector = self.embedding_fn(old_content)

                            points_to_update.append(
                                PointStruct(
                                    id=old_point_id,
                                    vector=old_vector,
                                    payload=deprecated_payload,
                                )
                            )

            # Batch update all points
            if points_to_update:
                self.client.upsert(
                    collection_name=self.collection_name,
                    wait=True,
                    points=points_to_update,
                )

            return CommitResult(ok=True, committed_ids=committed_ids)

        except Exception as e:
            return CommitResult(ok=False, error=f"Commit failed: {e}")

    def search(
        self, query: str, *, filters: Dict[str, Any], top_k: int = 8
    ) -> List[Dict[str, Any]]:
        """Search active memories using vector similarity.

        Args:
            query: Search query string
            filters: Additional filters (scope, user_id, project_id, etc.)
            top_k: Maximum number of results

        Returns:
            List of memory items matching the query
        """
        # Convert query to vector
        query_vector = self.embedding_fn(query)

        # Build filter for active status + user filters
        filter_conditions = [
            FieldCondition(key="status", match=MatchValue(value="active"))
        ]

        # Add scope filters
        for key, value in filters.items():
            if value is not None:
                filter_conditions.append(
                    FieldCondition(key=key, match=MatchValue(value=value))
                )

        search_filter = Filter(must=filter_conditions) if filter_conditions else None

        try:
            # Search Qdrant
            # Note: Qdrant search API may vary by version
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=search_filter,
                limit=top_k,
                with_payload=True,
                score_threshold=0.0,  # Lower threshold for testing
            )

            # Convert to memory item format
            results: List[Dict[str, Any]] = []
            for scored_point in search_result:
                payload = scored_point.payload or {}
                memory_id = payload.get("memory_id") or str(scored_point.id)

                item: Dict[str, Any] = {
                    "_schema_version": "2.1",
                    "memory_id": memory_id,
                    "type": payload.get("type", "fact"),
                    "scope": payload.get("scope", "global"),
                    "user_id": payload.get("user_id"),
                    "project_id": payload.get("project_id"),
                    "content": payload.get("content", ""),
                    "confidence": float(payload.get("confidence", 0.8)),
                    "status": "active",
                    "source_refs": payload.get("source_refs", []),
                    "created_at": payload.get("created_at", utc_iso()),
                    "updated_at": payload.get("updated_at", utc_iso()),
                    "_score": float(scored_point.score or 0.0),
                }

                # Add supersedes if present
                if "supersedes" in payload:
                    item["supersedes"] = payload["supersedes"]

                results.append(item)

            return results

        except Exception as e:
            # Return empty list on error
            return []

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all active memory items (for debugging).

        Returns:
            List of all active memory items
        """
        filter_condition = Filter(
            must=[FieldCondition(key="status", match=MatchValue(value="active"))]
        )

        try:
            scroll_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=filter_condition,
                limit=10000,
                with_payload=True,
                with_vectors=False,
            )

            results: List[Dict[str, Any]] = []
            for point in scroll_result[0]:
                point_id = point.id
                payload = point.payload or {}
                memory_id = payload.get("memory_id") or str(point_id)
                item: Dict[str, Any] = {
                    "_schema_version": "2.1",
                    "memory_id": memory_id,
                    "type": payload.get("type", "fact"),
                    "scope": payload.get("scope", "global"),
                    "user_id": payload.get("user_id"),
                    "project_id": payload.get("project_id"),
                    "content": payload.get("content", ""),
                    "confidence": float(payload.get("confidence", 0.8)),
                    "status": "active",
                    "source_refs": payload.get("source_refs", []),
                    "created_at": payload.get("created_at", utc_iso()),
                    "updated_at": payload.get("updated_at", utc_iso()),
                }

                if "supersedes" in payload:
                    item["supersedes"] = payload["supersedes"]

                results.append(item)

            return results

        except Exception as e:
            return []

