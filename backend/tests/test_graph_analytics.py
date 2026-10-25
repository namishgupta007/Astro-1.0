"""Tests validating graph analytics, centrality intelligence, and community detection.

Phase 1 Verification:
1. Empty graphs and single-node graphs work without error.
2. Centrality metrics are finite, non-negative, and normalized.
3. Community detection handles disconnected graphs and isolated nodes.
4. Every analytics result refers to an existing graph node.
5. Analytics do not introduce broken edges or change underlying graph structure.
6. Repeated analysis of identical input produces deterministic results.
7. Multi-repository analysis ensures strict isolation without global state leakage.
8. Existing API response contracts remain compatible and new endpoints return valid data.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import networkx as nx

from app.api.schemas import GraphResponse, RepositoryAnalyticsResponse
from app.config import settings
from app.graph.models import (
    EDGE_TYPE_CALLS,
    EDGE_TYPE_CONTAINS,
    EDGE_TYPE_DEFINES,
    EDGE_TYPE_IMPORTS,
    NODE_TYPE_CLASS,
    NODE_TYPE_DIRECTORY,
    NODE_TYPE_FILE,
    NODE_TYPE_FUNCTION,
    NODE_TYPE_METHOD,
    NODE_TYPE_REPOSITORY,
    CodeGraph,
    GraphEdge,
    GraphNode,
    GraphSummary,
)
from app.main import app
from app.services.graph_analytics_service import (
    GraphAnalyticsService,
    build_networkx_graph,
    compute_communities,
    compute_degree_metrics,
    compute_pagerank,
    graph_analytics_service,
)
from app.storage.database import init_db
from app.storage.repository_store import (
    create_job,
    create_repository,
    update_job,
    update_repository_status,
)


class TestGraphAnalyticsEdgeCases(unittest.TestCase):
    """Test resilience against edge cases: empty graphs, single-node, isolated, and cycles."""

    def setUp(self) -> None:
        self.service = GraphAnalyticsService()

    def test_empty_graph(self) -> None:
        """Empty graph produces safe, non-crashing empty analytics structures."""
        empty_graph = {
            "schema_version": 1,
            "repository": {"id": "repo:empty", "name": "empty"},
            "summary": {},
            "nodes": [],
            "edges": [],
            "unresolved_references": [],
        }

        analytics = self.service.compute_analytics(empty_graph, repository_id="empty")
        summary = analytics["summary"]

        self.assertEqual(summary["node_count"], 0)
        self.assertEqual(summary["edge_count"], 0)
        self.assertEqual(summary["cluster_count"], 0)
        self.assertEqual(summary["density"], 0.0)
        self.assertFalse(summary["is_connected"])
        self.assertEqual(summary["connected_components_count"], 0)
        self.assertEqual(analytics["nodes"], [])
        self.assertEqual(analytics["clusters"], {})

    def test_single_node_graph(self) -> None:
        """Single node graph has finite metrics, valid PageRank of 1.0, and belongs to cluster 0."""
        single_node_graph = {
            "schema_version": 1,
            "repository": {"id": "repo:solo", "name": "solo"},
            "summary": {},
            "nodes": [
                {
                    "id": "repo:solo",
                    "type": NODE_TYPE_REPOSITORY,
                    "name": "solo",
                    "label": "solo",
                    "metadata": {},
                }
            ],
            "edges": [],
            "unresolved_references": [],
        }

        analytics = self.service.compute_analytics(single_node_graph, repository_id="solo")
        summary = analytics["summary"]

        self.assertEqual(summary["node_count"], 1)
        self.assertEqual(summary["edge_count"], 0)
        self.assertEqual(summary["cluster_count"], 1)
        self.assertEqual(len(analytics["nodes"]), 1)

        node = analytics["nodes"][0]
        self.assertEqual(node["id"], "repo:solo")
        self.assertEqual(node["cluster_id"], 0)
        self.assertEqual(node["metrics"]["pagerank"], 1.0)
        self.assertEqual(node["metrics"]["normalized_centrality"], 1.0)
        self.assertEqual(node["metrics"]["in_degree"], 0)
        self.assertEqual(node["metrics"]["out_degree"], 0)
        self.assertIn(node["metrics"]["degree_centrality"], (0.0, 1.0))

    def test_all_isolated_nodes(self) -> None:
        """Graph with multiple disconnected nodes without any edges."""
        graph = {
            "schema_version": 1,
            "repository": {"id": "repo:iso", "name": "iso"},
            "summary": {},
            "nodes": [
                {"id": f"file:mod{i}.py", "type": NODE_TYPE_FILE, "name": f"mod{i}.py", "label": f"mod{i}.py"}
                for i in range(5)
            ],
            "edges": [],
            "unresolved_references": [],
        }

        analytics = self.service.compute_analytics(graph)
        summary = analytics["summary"]

        self.assertEqual(summary["node_count"], 5)
        self.assertEqual(summary["edge_count"], 0)
        # All isolated nodes belong to cluster 0
        self.assertEqual(summary["cluster_count"], 1)
        for n in analytics["nodes"]:
            self.assertEqual(n["cluster_id"], 0)
            self.assertEqual(n["metrics"]["in_degree"], 0)
            self.assertEqual(n["metrics"]["out_degree"], 0)
            self.assertEqual(n["metrics"]["degree_centrality"], 0.0)
            self.assertGreater(n["metrics"]["pagerank"], 0.0)

    def test_cycles_and_mutual_dependencies(self) -> None:
        """Graph with circular call and import cycles converges properly."""
        graph = {
            "schema_version": 1,
            "repository": {"id": "repo:cycle", "name": "cycle"},
            "summary": {},
            "nodes": [
                {"id": "func:a", "type": NODE_TYPE_FUNCTION, "name": "a", "label": "a()"},
                {"id": "func:b", "type": NODE_TYPE_FUNCTION, "name": "b", "label": "b()"},
                {"id": "func:c", "type": NODE_TYPE_FUNCTION, "name": "c", "label": "c()"},
            ],
            "edges": [
                {"id": "e1", "source": "func:a", "target": "func:b", "type": EDGE_TYPE_CALLS},
                {"id": "e2", "source": "func:b", "target": "func:c", "type": EDGE_TYPE_CALLS},
                {"id": "e3", "source": "func:c", "target": "func:a", "type": EDGE_TYPE_CALLS},
            ],
            "unresolved_references": [],
        }

        analytics = self.service.compute_analytics(graph)
        summary = analytics["summary"]

        self.assertEqual(summary["node_count"], 3)
        self.assertEqual(summary["edge_count"], 3)
        self.assertTrue(summary["is_connected"])
        for n in analytics["nodes"]:
            self.assertEqual(n["metrics"]["in_degree"], 1)
            self.assertEqual(n["metrics"]["out_degree"], 1)
            # In symmetric 3-cycle, normalized centrality should be equal
            self.assertEqual(n["metrics"]["normalized_centrality"], 1.0)

    def test_self_loops_handled_gracefully(self) -> None:
        """Self-referential recursive calls do not crash community or centrality detection."""
        graph = {
            "schema_version": 1,
            "repository": {"id": "repo:recurse", "name": "recurse"},
            "summary": {},
            "nodes": [
                {"id": "func:factorial", "type": NODE_TYPE_FUNCTION, "name": "factorial", "label": "factorial()"},
            ],
            "edges": [
                {"id": "e_self", "source": "func:factorial", "target": "func:factorial", "type": EDGE_TYPE_CALLS},
            ],
            "unresolved_references": [],
        }

        analytics = self.service.compute_analytics(graph)
        self.assertEqual(analytics["summary"]["node_count"], 1)
        self.assertEqual(analytics["summary"]["edge_count"], 1)
        node = analytics["nodes"][0]
        self.assertEqual(node["id"], "func:factorial")
        self.assertEqual(node["metrics"]["in_degree"], 1)
        self.assertEqual(node["metrics"]["out_degree"], 1)


class TestCentralityMetrics(unittest.TestCase):
    """Test mathematical properties of centrality metrics."""

    def setUp(self) -> None:
        self.service = GraphAnalyticsService()

    def test_centrality_bounds_and_finite_values(self) -> None:
        """All centrality metrics must be finite, non-negative, and in [0.0, 1.0]."""
        graph = {
            "schema_version": 1,
            "repository": {"id": "repo:topo", "name": "topo"},
            "summary": {},
            "nodes": [
                {"id": "repo:root", "type": NODE_TYPE_REPOSITORY, "name": "root", "label": "root"},
                {"id": "dir:src", "type": NODE_TYPE_DIRECTORY, "name": "src", "label": "src"},
                {"id": "file:main.py", "type": NODE_TYPE_FILE, "name": "main.py", "label": "main.py"},
                {"id": "file:utils.py", "type": NODE_TYPE_FILE, "name": "utils.py", "label": "utils.py"},
                {"id": "func:run", "type": NODE_TYPE_FUNCTION, "name": "run", "label": "run()"},
                {"id": "func:helper", "type": NODE_TYPE_FUNCTION, "name": "helper", "label": "helper()"},
            ],
            "edges": [
                {"id": "e1", "source": "repo:root", "target": "dir:src", "type": EDGE_TYPE_CONTAINS},
                {"id": "e2", "source": "dir:src", "target": "file:main.py", "type": EDGE_TYPE_CONTAINS},
                {"id": "e3", "source": "dir:src", "target": "file:utils.py", "type": EDGE_TYPE_CONTAINS},
                {"id": "e4", "source": "file:main.py", "target": "func:run", "type": EDGE_TYPE_DEFINES},
                {"id": "e5", "source": "file:utils.py", "target": "func:helper", "type": EDGE_TYPE_DEFINES},
                {"id": "e6", "source": "func:run", "target": "func:helper", "type": EDGE_TYPE_CALLS},
                {"id": "e7", "source": "file:main.py", "target": "file:utils.py", "type": EDGE_TYPE_IMPORTS},
            ],
            "unresolved_references": [],
        }

        analytics = self.service.compute_analytics(graph)
        for node in analytics["nodes"]:
            m = node["metrics"]
            # PageRank
            self.assertTrue(0.0 <= m["pagerank"] <= 1.0)
            self.assertTrue(0.0 <= m["normalized_centrality"] <= 1.0)
            # Degree metrics
            self.assertGreaterEqual(m["in_degree"], 0)
            self.assertGreaterEqual(m["out_degree"], 0)
            self.assertTrue(0.0 <= m["degree_centrality"] <= 1.0)
            self.assertTrue(0.0 <= m["in_degree_centrality"] <= 1.0)
            self.assertTrue(0.0 <= m["out_degree_centrality"] <= 1.0)

    def test_hub_node_has_highest_centrality(self) -> None:
        """A central utility function called by multiple callers has high in-degree and PageRank."""
        nodes = [{"id": f"caller_{i}", "type": NODE_TYPE_FUNCTION, "name": f"caller_{i}", "label": f"caller_{i}()"} for i in range(5)]
        nodes.append({"id": "target_hub", "type": NODE_TYPE_FUNCTION, "name": "hub", "label": "hub()"})

        edges = [{"id": f"e_{i}", "source": f"caller_{i}", "target": "target_hub", "type": EDGE_TYPE_CALLS} for i in range(5)]

        graph = {
            "schema_version": 1,
            "repository": {"id": "repo:star", "name": "star"},
            "summary": {},
            "nodes": nodes,
            "edges": edges,
            "unresolved_references": [],
        }

        analytics = self.service.compute_analytics(graph)
        node_map = {n["id"]: n for n in analytics["nodes"]}

        hub = node_map["target_hub"]
        self.assertEqual(hub["metrics"]["in_degree"], 5)
        self.assertEqual(hub["metrics"]["out_degree"], 0)
        self.assertEqual(hub["metrics"]["normalized_centrality"], 1.0)

        for i in range(5):
            caller = node_map[f"caller_{i}"]
            self.assertEqual(caller["metrics"]["in_degree"], 0)
            self.assertEqual(caller["metrics"]["out_degree"], 1)
            self.assertLess(caller["metrics"]["pagerank"], hub["metrics"]["pagerank"])


class TestCommunityDetection(unittest.TestCase):
    """Test community clustering stability, determinism, and disconnected graph handling."""

    def setUp(self) -> None:
        self.service = GraphAnalyticsService()

    def test_disconnected_subgraphs_detected_as_distinct_communities(self) -> None:
        """Two separated modules form distinct community clusters."""
        graph = {
            "schema_version": 1,
            "repository": {"id": "repo:two_clusters", "name": "two_clusters"},
            "summary": {},
            "nodes": [
                # Cluster A
                {"id": "file:a1.py", "type": NODE_TYPE_FILE, "name": "a1", "label": "a1"},
                {"id": "file:a2.py", "type": NODE_TYPE_FILE, "name": "a2", "label": "a2"},
                {"id": "file:a3.py", "type": NODE_TYPE_FILE, "name": "a3", "label": "a3"},
                # Cluster B
                {"id": "file:b1.py", "type": NODE_TYPE_FILE, "name": "b1", "label": "b1"},
                {"id": "file:b2.py", "type": NODE_TYPE_FILE, "name": "b2", "label": "b2"},
                {"id": "file:b3.py", "type": NODE_TYPE_FILE, "name": "b3", "label": "b3"},
            ],
            "edges": [
                # Internal to A
                {"id": "ea1", "source": "file:a1.py", "target": "file:a2.py", "type": EDGE_TYPE_IMPORTS},
                {"id": "ea2", "source": "file:a2.py", "target": "file:a3.py", "type": EDGE_TYPE_IMPORTS},
                # Internal to B
                {"id": "eb1", "source": "file:b1.py", "target": "file:b2.py", "type": EDGE_TYPE_IMPORTS},
                {"id": "eb2", "source": "file:b2.py", "target": "file:b3.py", "type": EDGE_TYPE_IMPORTS},
            ],
            "unresolved_references": [],
        }

        analytics = self.service.compute_analytics(graph)
        node_map = {n["id"]: n for n in analytics["nodes"]}

        # All nodes in cluster A have the same cluster_id
        cluster_a = node_map["file:a1.py"]["cluster_id"]
        self.assertEqual(node_map["file:a2.py"]["cluster_id"], cluster_a)
        self.assertEqual(node_map["file:a3.py"]["cluster_id"], cluster_a)

        # All nodes in cluster B have the same cluster_id
        cluster_b = node_map["file:b1.py"]["cluster_id"]
        self.assertEqual(node_map["file:b2.py"]["cluster_id"], cluster_b)
        self.assertEqual(node_map["file:b3.py"]["cluster_id"], cluster_b)

        # Clusters A and B must be distinct
        self.assertNotEqual(cluster_a, cluster_b)
        self.assertEqual(analytics["summary"]["cluster_count"], 2)

    def test_community_determinism_across_repeated_runs(self) -> None:
        """Running community detection 10 times on identical input produces identical cluster IDs."""
        G = nx.DiGraph()
        for i in range(15):
            G.add_node(f"node_{i}")
        # Add a mix of edges
        for i in range(5):
            G.add_edge(f"node_{i}", f"node_{(i+1)%5}")
        for i in range(5, 10):
            G.add_edge(f"node_{i}", f"node_{5 + ((i+1)%5)}")
        for i in range(10, 15):
            G.add_edge(f"node_{i}", f"node_{10 + ((i+1)%5)}")

        first_partition = compute_communities(G, seed=42)
        for _ in range(10):
            repeated_partition = compute_communities(G, seed=42)
            self.assertEqual(first_partition, repeated_partition)


class TestGraphIntegrityAndImmutability(unittest.TestCase):
    """Ensure graph analytics does not invent nodes, mutate schemas, or alter graph topology."""

    def setUp(self) -> None:
        self.service = GraphAnalyticsService()

    def test_all_analytics_nodes_refer_to_existing_graph_nodes(self) -> None:
        """Every analytics result refers strictly to a real node from the graph."""
        original_nodes = [
            GraphNode(id="repo:demo", type=NODE_TYPE_REPOSITORY, name="demo", label="demo"),
            GraphNode(id="file:demo.py", type=NODE_TYPE_FILE, name="demo.py", label="demo.py"),
            GraphNode(id="class:Service", type=NODE_TYPE_CLASS, name="Service", label="Service"),
            GraphNode(id="method:Service.run", type=NODE_TYPE_METHOD, name="run", label="run()"),
        ]
        original_edges = [
            GraphEdge(id="e1", source="repo:demo", target="file:demo.py", type=EDGE_TYPE_CONTAINS),
            GraphEdge(id="e2", source="file:demo.py", target="class:Service", type=EDGE_TYPE_DEFINES),
            GraphEdge(id="e3", source="class:Service", target="method:Service.run", type=EDGE_TYPE_DEFINES),
        ]
        code_graph = CodeGraph(
            schema_version=1,
            repository={"id": "repo:demo", "name": "demo"},
            summary=GraphSummary(node_count=4, edge_count=3),
            nodes=original_nodes,
            edges=original_edges,
        )

        analytics = self.service.compute_analytics(code_graph)
        original_ids = {n.id for n in original_nodes}
        analytics_ids = {n["id"] for n in analytics["nodes"]}

        self.assertEqual(original_ids, analytics_ids)

    def test_enrich_preserves_underlying_graph_structure(self) -> None:
        """enrich_graph_data leaves node IDs, edge IDs, sources, targets, and unresolved refs untouched."""
        graph_dict = {
            "schema_version": 1,
            "repository": {"id": "repo:immut", "name": "immut"},
            "summary": {"node_count": 2, "edge_count": 1},
            "nodes": [
                {"id": "file:a.py", "type": NODE_TYPE_FILE, "name": "a.py", "label": "a.py", "metadata": {"loc": 50}},
                {"id": "file:b.py", "type": NODE_TYPE_FILE, "name": "b.py", "label": "b.py", "metadata": {"loc": 25}},
            ],
            "edges": [
                {"id": "e_ab", "source": "file:a.py", "target": "file:b.py", "type": EDGE_TYPE_IMPORTS, "metadata": {}},
            ],
            "unresolved_references": [{"kind": "import", "expression": "unknown_pkg"}],
        }

        # Deep copy for verification
        snapshot = json.loads(json.dumps(graph_dict))

        enriched = self.service.enrich_graph_data(graph_dict)

        # Core topology remains identical
        self.assertEqual(len(enriched["nodes"]), len(snapshot["nodes"]))
        self.assertEqual(len(enriched["edges"]), len(snapshot["edges"]))
        self.assertEqual(enriched["edges"][0]["source"], "file:a.py")
        self.assertEqual(enriched["edges"][0]["target"], "file:b.py")
        self.assertEqual(enriched["unresolved_references"], snapshot["unresolved_references"])

        # Nodes have received analytics metadata without destroying existing metadata
        self.assertEqual(enriched["nodes"][0]["metadata"]["loc"], 50)
        self.assertIn("centrality", enriched["nodes"][0]["metadata"])
        self.assertIn("cluster_id", enriched["nodes"][0]["metadata"])
        self.assertIn("pagerank", enriched["nodes"][0]["metadata"])

    def test_broken_edges_pointing_to_nonexistent_nodes_are_discarded_safely(self) -> None:
        """NetworkX graph construction filters out broken edge endpoints rather than crashing."""
        graph = {
            "schema_version": 1,
            "repository": {"id": "repo:broken", "name": "broken"},
            "summary": {},
            "nodes": [
                {"id": "file:real.py", "type": NODE_TYPE_FILE, "name": "real.py", "label": "real.py"},
            ],
            "edges": [
                # Edge pointing to non-existent target
                {"id": "e_broken", "source": "file:real.py", "target": "file:ghost.py", "type": EDGE_TYPE_IMPORTS},
            ],
            "unresolved_references": [],
        }

        G = build_networkx_graph(graph)
        self.assertEqual(G.number_of_nodes(), 1)
        self.assertEqual(G.number_of_edges(), 0)

        analytics = self.service.compute_analytics(graph)
        self.assertEqual(analytics["summary"]["node_count"], 1)
        self.assertEqual(analytics["summary"]["edge_count"], 0)


class TestRepositoryIsolationAndAPI(unittest.TestCase):
    """Test multi-repository isolation, REST API endpoints, and backward compatibility."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_path = Path(self.temp_dir.name).resolve()

        # Isolate database and storage directories for this test run
        self.orig_data_dir = settings.data_dir
        settings.data_dir = self.temp_path / "data"
        settings.ensure_directories()
        init_db()

        self.client = TestClient(app)

    def tearDown(self) -> None:
        settings.data_dir = self.orig_data_dir
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_multi_repository_isolation(self) -> None:
        """Analyzing two repositories preserves strictly isolated data without cross-contamination."""
        repo_a_id = "repo_alpha"
        repo_b_id = "repo_beta"

        art_a = settings.get_repo_artifact_dir(repo_a_id)
        art_b = settings.get_repo_artifact_dir(repo_b_id)
        art_a.mkdir(parents=True, exist_ok=True)
        art_b.mkdir(parents=True, exist_ok=True)

        # Repo A has 2 nodes
        graph_a = {
            "schema_version": 1,
            "repository": {"id": repo_a_id, "name": "alpha"},
            "summary": {"node_count": 2, "edge_count": 1},
            "nodes": [
                {"id": "node_a1", "type": NODE_TYPE_FILE, "name": "a1", "label": "a1"},
                {"id": "node_a2", "type": NODE_TYPE_FILE, "name": "a2", "label": "a2"},
            ],
            "edges": [{"id": "e_a", "source": "node_a1", "target": "node_a2", "type": EDGE_TYPE_CALLS}],
            "unresolved_references": [],
        }
        (art_a / "code_graph.json").write_text(json.dumps(graph_a), encoding="utf-8")

        # Repo B has 3 nodes
        graph_b = {
            "schema_version": 1,
            "repository": {"id": repo_b_id, "name": "beta"},
            "summary": {"node_count": 3, "edge_count": 2},
            "nodes": [
                {"id": "node_b1", "type": NODE_TYPE_FILE, "name": "b1", "label": "b1"},
                {"id": "node_b2", "type": NODE_TYPE_FILE, "name": "b2", "label": "b2"},
                {"id": "node_b3", "type": NODE_TYPE_FILE, "name": "b3", "label": "b3"},
            ],
            "edges": [
                {"id": "e_b1", "source": "node_b1", "target": "node_b2", "type": EDGE_TYPE_CALLS},
                {"id": "e_b2", "source": "node_b2", "target": "node_b3", "type": EDGE_TYPE_CALLS},
            ],
            "unresolved_references": [],
        }
        (art_b / "code_graph.json").write_text(json.dumps(graph_b), encoding="utf-8")

        res_a = graph_analytics_service.compute_and_save_repository_analytics(
            repo_id=repo_a_id,
            code_graph_path=art_a / "code_graph.json",
            output_path=art_a / "graph_analytics.json",
        )
        res_b = graph_analytics_service.compute_and_save_repository_analytics(
            repo_id=repo_b_id,
            code_graph_path=art_b / "code_graph.json",
            output_path=art_b / "graph_analytics.json",
        )

        self.assertEqual(res_a["summary"]["node_count"], 2)
        self.assertEqual(res_b["summary"]["node_count"], 3)
        self.assertNotIn("node_b1", {n["id"] for n in res_a["nodes"]})
        self.assertNotIn("node_a1", {n["id"] for n in res_b["nodes"]})

    def test_analytics_api_endpoint(self) -> None:
        """GET /api/repositories/{id}/analytics returns 200 and conforms to RepositoryAnalyticsResponse."""
        repo_id = "repo_api_test"
        create_repository(
            repo_id=repo_id,
            url="https://github.com/example/api_test",
            owner="example",
            name="api_test",
            branch="main",
            workspace_dir=str(self.temp_path / repo_id / "source"),
            artifact_dir=str(settings.get_repo_artifact_dir(repo_id)),
        )
        update_repository_status(repo_id, status="completed")

        art_dir = settings.get_repo_artifact_dir(repo_id)
        art_dir.mkdir(parents=True, exist_ok=True)

        graph_payload = {
            "schema_version": 1,
            "repository": {"id": repo_id, "name": "api_test"},
            "summary": {"node_count": 2, "edge_count": 1},
            "nodes": [
                {"id": "file:srv.py", "type": NODE_TYPE_FILE, "name": "srv.py", "label": "srv.py"},
                {"id": "func:serve", "type": NODE_TYPE_FUNCTION, "name": "serve", "label": "serve()"},
            ],
            "edges": [
                {"id": "e1", "source": "file:srv.py", "target": "func:serve", "type": EDGE_TYPE_DEFINES},
            ],
            "unresolved_references": [],
        }
        (art_dir / "code_graph.json").write_text(json.dumps(graph_payload), encoding="utf-8")

        response = self.client.get(f"/api/repositories/{repo_id}/analytics")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        validated = RepositoryAnalyticsResponse.model_validate(data)
        self.assertEqual(validated.repository_id, repo_id)
        self.assertEqual(validated.summary.node_count, 2)
        self.assertEqual(validated.summary.edge_count, 1)
        self.assertGreaterEqual(validated.summary.cluster_count, 1)

    def test_analytics_endpoint_status_guards(self) -> None:
        """Analytics endpoint returns 404 for missing repo and 409 when repo is still running."""
        # 404
        res_404 = self.client.get("/api/repositories/non_existent_repo/analytics")
        self.assertEqual(res_404.status_code, 404)

        # 409
        unready_id = "repo_running"
        create_repository(
            repo_id=unready_id,
            url="https://github.com/example/running",
            owner="example",
            name="running",
            branch="main",
            workspace_dir="",
            artifact_dir="",
            status="running",
        )
        res_409 = self.client.get(f"/api/repositories/{unready_id}/analytics")
        self.assertEqual(res_409.status_code, 409)

    def test_graph_endpoint_backward_compatibility(self) -> None:
        """Existing GET /api/repositories/{id}/graph returns original schema plus optional analytics."""
        repo_id = "repo_compat"
        create_repository(
            repo_id=repo_id,
            url="https://github.com/example/compat",
            owner="example",
            name="compat",
            branch="main",
            workspace_dir="",
            artifact_dir=str(settings.get_repo_artifact_dir(repo_id)),
            status="completed",
        )

        art_dir = settings.get_repo_artifact_dir(repo_id)
        art_dir.mkdir(parents=True, exist_ok=True)

        graph_payload = {
            "schema_version": 1,
            "repository": {"id": repo_id, "name": "compat"},
            "summary": {
                "node_count": 2,
                "edge_count": 1,
                "nodes_by_type": {"file": 1, "function": 1},
                "edges_by_type": {"DEFINES": 1},
                "resolved_calls": 0,
                "ambiguous_calls": 0,
                "unresolved_calls": 0,
                "resolved_imports": 0,
                "unresolved_imports": 0,
            },
            "nodes": [
                {"id": "file:c.py", "type": NODE_TYPE_FILE, "name": "c.py", "label": "c.py", "metadata": {}},
                {"id": "func:f", "type": NODE_TYPE_FUNCTION, "name": "f", "label": "f()", "metadata": {}},
            ],
            "edges": [
                {"id": "ec1", "source": "file:c.py", "target": "func:f", "type": EDGE_TYPE_DEFINES, "metadata": {}},
            ],
            "unresolved_references": [],
        }
        (art_dir / "code_graph.json").write_text(json.dumps(graph_payload), encoding="utf-8")

        # Also precompute analytics
        graph_analytics_service.compute_and_save_repository_analytics(
            repo_id=repo_id,
            code_graph_path=art_dir / "code_graph.json",
            output_path=art_dir / "graph_analytics.json",
        )

        res = self.client.get(f"/api/repositories/{repo_id}/graph")
        self.assertEqual(res.status_code, 200)

        data = res.json()
        validated = GraphResponse.model_validate(data)
        self.assertEqual(validated.repository_id, repo_id)
        self.assertEqual(validated.schema_version, 1)
        self.assertEqual(len(validated.nodes), 2)
        self.assertEqual(len(validated.edges), 1)

        # Enriched metadata exists on node
        node_c = next(n for n in validated.nodes if n.id == "file:c.py")
        self.assertIn("centrality", node_c.metadata)
        self.assertIn("cluster_id", node_c.metadata)

        # Optional analytics field is populated
        self.assertIsNotNone(validated.analytics)
        self.assertEqual(validated.analytics.node_count, 2)
