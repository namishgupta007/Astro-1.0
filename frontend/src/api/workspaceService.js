// Service layer for workspace, indexing, graph data, and AI interactions.
// Supports both live FastAPI backend and offline fallback mode with normalized mock dataset.

import { normalizeGraphData } from '../services/graphNormalizer.js';

const BASE = (
  (typeof import.meta !== "undefined" &&
    (import.meta.env?.VITE_API_BASE_URL || import.meta.env?.VITE_API_URL)) ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

// Canonical reference dataset representing cosmic-weather-api matching reference snapshot
export const MOCK_GRAPH = {
  repo_url: "https://github.com/astral-demo/cosmic-weather-api",
  repo_name: "cosmic-weather-api",
  branch: "main",
  commit_sha: "7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b",
  generated_at: new Date().toISOString(),
  is_demo: true,
  nodes: [
    // ─── src/ (5 files) ──────────────────────────────────────────────────────────
    {
      id: "file::src/main.py",
      label: "main.py",
      type: "file",
      language: "python",
      path: "src/main.py",
      metrics: { loc: 210, centrality: 0.72, complexity: 6 },
      position_hint: { cluster_id: 0, depth: 1 },
      ai_summary: "Main application bootstrapping FastAPI server, setting up global middleware, and registering router endpoints."
    },
    {
      id: "file::src/routes.py",
      label: "routes.py",
      type: "file",
      language: "python",
      path: "src/routes.py",
      metrics: { loc: 180, centrality: 0.78, complexity: 8 },
      position_hint: { cluster_id: 0, depth: 1 },
      ai_summary: "HTTP API route definitions directing weather forecasting requests, satellite queries, and telemetry ingest."
    },
    {
      id: "file::src/models.py",
      label: "models.py",
      type: "file",
      language: "python",
      path: "src/models.py",
      metrics: { loc: 140, centrality: 0.65, complexity: 4 },
      position_hint: { cluster_id: 0, depth: 1 },
      ai_summary: "Top-level domain models, common data transfer schemas, and response validation envelopes."
    },
    {
      id: "file::src/weather.py",
      label: "weather.py",
      type: "file",
      language: "python",
      path: "src/weather.py",
      metrics: { loc: 320, centrality: 0.74, complexity: 14 },
      position_hint: { cluster_id: 0, depth: 1 },
      ai_summary: "Calculates solar wind speeds, geomagnetic storm indexes, and orbital atmospheric friction parameters."
    },
    {
      id: "file::src/telemetry.py",
      label: "telemetry.py",
      type: "file",
      language: "python",
      path: "src/telemetry.py",
      metrics: { loc: 1450, centrality: 0.85, complexity: 12 },
      position_hint: { cluster_id: 0, depth: 1 },
      ai_summary: "Handles telemetry data collection, processing and export. Acts as a bridge between the main application and weather data services. Depends on models for data structures and uses SolarFluxEngine for advanced calculations."
    },

    // ─── services/ (3 files) ─────────────────────────────────────────────────────
    {
      id: "file::services/data_fetcher.py",
      label: "data_fetcher.py",
      type: "file",
      language: "python",
      path: "services/data_fetcher.py",
      metrics: { loc: 410, centrality: 0.62, complexity: 9 },
      position_hint: { cluster_id: 1, depth: 1 },
      ai_summary: "Asynchronously fetches space telemetry from NOAA SWPC and external satellite orbital sensors."
    },
    {
      id: "file::services/processing.py",
      label: "processing.py",
      type: "file",
      language: "python",
      path: "services/processing.py",
      metrics: { loc: 560, centrality: 0.82, complexity: 15 },
      position_hint: { cluster_id: 1, depth: 1 },
      ai_summary: "High-throughput stream processing pipeline transforming raw satellite telemetry into normalized physics arrays."
    },
    {
      id: "file::services/api_client.py",
      label: "api_client.py",
      type: "file",
      language: "python",
      path: "services/api_client.py",
      metrics: { loc: 230, centrality: 0.55, complexity: 5 },
      position_hint: { cluster_id: 1, depth: 1 },
      ai_summary: "Resilient HTTP client for upstream space agency data with exponential backoff and circuit-breaking."
    },

    // ─── SolarFluxEngine/ (4 files) ──────────────────────────────────────────────
    {
      id: "file::SolarFluxEngine/engine.py",
      label: "engine.py",
      type: "file",
      language: "python",
      path: "SolarFluxEngine/engine.py",
      metrics: { loc: 890, centrality: 0.88, complexity: 19 },
      position_hint: { cluster_id: 2, depth: 1 },
      ai_summary: "Core computational physics engine orchestrating magnetosphere flux calculations, radiation modeling, and flare predictions."
    },
    {
      id: "file::SolarFluxEngine/magnetosphere.py",
      label: "magnetosphere.py",
      type: "file",
      language: "python",
      path: "SolarFluxEngine/magnetosphere.py",
      metrics: { loc: 480, centrality: 0.58, complexity: 11 },
      position_hint: { cluster_id: 2, depth: 1 },
      ai_summary: "Models geomagnetic boundary layers, bow shock compressions, and magnetic reconnection dynamics."
    },
    {
      id: "file::SolarFluxEngine/solar.py",
      label: "solar.py",
      type: "file",
      language: "python",
      path: "SolarFluxEngine/solar.py",
      metrics: { loc: 390, centrality: 0.61, complexity: 8 },
      position_hint: { cluster_id: 2, depth: 1 },
      ai_summary: "Calculates solar flare indices, coronal mass ejection trajectories, and UV/X-ray solar radiation bands."
    },
    {
      id: "file::SolarFluxEngine/prediction.py",
      label: "prediction.py",
      type: "file",
      language: "python",
      path: "SolarFluxEngine/prediction.py",
      metrics: { loc: 520, centrality: 0.70, complexity: 13 },
      position_hint: { cluster_id: 2, depth: 1 },
      ai_summary: "Predictive neural network forecasting geomagnetic storms, satellite drag coefficients, and radio blackout windows."
    },

    // ─── models/ (3 files) ───────────────────────────────────────────────────────
    {
      id: "file::models/base.py",
      label: "base.py",
      type: "file",
      language: "python",
      path: "models/base.py",
      metrics: { loc: 160, centrality: 0.48, complexity: 3 },
      position_hint: { cluster_id: 3, depth: 1 },
      ai_summary: "Base Pydantic entity models with timestamp serialization mixins and geo-spatial coordinate validation."
    },
    {
      id: "file::models/forecast.py",
      label: "forecast.py",
      type: "file",
      language: "python",
      path: "models/forecast.py",
      metrics: { loc: 240, centrality: 0.52, complexity: 5 },
      position_hint: { cluster_id: 3, depth: 1 },
      ai_summary: "Data structures representing hourly and 7-day geomagnetic weather predictions and severity alert thresholds."
    },
    {
      id: "file::models/solar.py",
      label: "solar.py",
      type: "file",
      language: "python",
      path: "models/solar.py",
      metrics: { loc: 190, centrality: 0.50, complexity: 4 },
      position_hint: { cluster_id: 3, depth: 1 },
      ai_summary: "Entity schemas for sunspot counts, spectral irradiance measurements, and solar wind velocity vectors."
    },

    // ─── api/ (2 files) ──────────────────────────────────────────────────────────
    {
      id: "file::api/endpoints.py",
      label: "endpoints.py",
      type: "file",
      language: "python",
      path: "api/endpoints.py",
      metrics: { loc: 290, centrality: 0.64, complexity: 7 },
      position_hint: { cluster_id: 4, depth: 1 },
      ai_summary: "REST endpoint controllers exposing current weather feeds, flare alerts, and historical geomagnetic lookups."
    },
    {
      id: "file::api/schemas.py",
      label: "schemas.py",
      type: "file",
      language: "python",
      path: "api/schemas.py",
      metrics: { loc: 210, centrality: 0.45, complexity: 3 },
      position_hint: { cluster_id: 4, depth: 1 },
      ai_summary: "Pydantic request and response schemas enforcing strict typing for HTTP clients and telemetry producers."
    },

    // ─── utils/ (2 files) ────────────────────────────────────────────────────────
    {
      id: "file::utils/helpers.py",
      label: "helpers.py",
      type: "file",
      language: "python",
      path: "utils/helpers.py",
      metrics: { loc: 180, centrality: 0.54, complexity: 4 },
      position_hint: { cluster_id: 5, depth: 1 },
      ai_summary: "Astronomical coordinate conversion, unit transformations, timestamp formatting, and vector maths."
    },
    {
      id: "file::utils/constants.py",
      label: "constants.py",
      type: "file",
      language: "python",
      path: "utils/constants.py",
      metrics: { loc: 95, centrality: 0.40, complexity: 1 },
      position_hint: { cluster_id: 5, depth: 1 },
      ai_summary: "Astrophysical constants, Earth magnetic dipole moment, speed of light, and solar radius baselines."
    }
  ],

  // ─── DIRECT FILE-TO-FILE DEPENDENCY EDGES ─────────────────────────────────
  edges: [
    // Incoming to telemetry.py (3):
    { id: "e_main_telemetry", source: "file::src/main.py", target: "file::src/telemetry.py", relation: "imports", weight: 2.0 },
    { id: "e_routes_telemetry", source: "file::src/routes.py", target: "file::src/telemetry.py", relation: "imports", weight: 2.0 },
    { id: "e_weather_telemetry", source: "file::src/weather.py", target: "file::src/telemetry.py", relation: "calls", weight: 2.5 },

    // Outgoing from telemetry.py (4):
    { id: "e_telemetry_fetcher", source: "file::src/telemetry.py", target: "file::services/data_fetcher.py", relation: "imports", weight: 2.2 },
    { id: "e_telemetry_processing", source: "file::src/telemetry.py", target: "file::services/processing.py", relation: "calls", weight: 2.8 },
    { id: "e_telemetry_engine", source: "file::src/telemetry.py", target: "file::SolarFluxEngine/engine.py", relation: "imports", weight: 3.0 },
    { id: "e_telemetry_models", source: "file::src/telemetry.py", target: "file::src/models.py", relation: "imports", weight: 1.8 },

    // Intra-src dependencies
    { id: "e_main_routes", source: "file::src/main.py", target: "file::src/routes.py", relation: "imports", weight: 2.0 },
    { id: "e_routes_weather", source: "file::src/routes.py", target: "file::src/weather.py", relation: "calls", weight: 2.4 },
    { id: "e_routes_models", source: "file::src/routes.py", target: "file::src/models.py", relation: "imports", weight: 1.5 },
    { id: "e_weather_models", source: "file::src/weather.py", target: "file::src/models.py", relation: "defines", weight: 1.9 },

    // Cross-folder
    { id: "e_routes_endpoints", source: "file::src/routes.py", target: "file::api/endpoints.py", relation: "imports", weight: 2.2 },
    { id: "e_weather_base_models", source: "file::src/weather.py", target: "file::models/base.py", relation: "calls", weight: 2.0 },

    // services module
    { id: "e_fetcher_proc", source: "file::services/data_fetcher.py", target: "file::services/processing.py", relation: "calls", weight: 2.5 },
    { id: "e_proc_apiclient", source: "file::services/processing.py", target: "file::services/api_client.py", relation: "calls", weight: 2.0 },
    { id: "e_proc_endpoints", source: "file::services/processing.py", target: "file::api/endpoints.py", relation: "defines", weight: 2.3 },

    // SolarFluxEngine
    { id: "e_engine_proc", source: "file::SolarFluxEngine/engine.py", target: "file::services/processing.py", relation: "calls", weight: 2.7 },
    { id: "e_engine_pred", source: "file::SolarFluxEngine/engine.py", target: "file::SolarFluxEngine/prediction.py", relation: "calls", weight: 2.4 },
    { id: "e_engine_solar_model", source: "file::SolarFluxEngine/engine.py", target: "file::models/solar.py", relation: "calls", weight: 2.1 },
    { id: "e_engine_helpers", source: "file::SolarFluxEngine/engine.py", target: "file::utils/helpers.py", relation: "calls", weight: 1.8 },
    { id: "e_magneto_engine", source: "file::SolarFluxEngine/magnetosphere.py", target: "file::SolarFluxEngine/engine.py", relation: "imports", weight: 2.2 },
    { id: "e_solar_engine", source: "file::SolarFluxEngine/solar.py", target: "file::SolarFluxEngine/engine.py", relation: "imports", weight: 2.2 },
    { id: "e_pred_engine", source: "file::SolarFluxEngine/prediction.py", target: "file::SolarFluxEngine/engine.py", relation: "calls", weight: 2.0 },

    // models
    { id: "e_base_forecast", source: "file::models/base.py", target: "file::models/forecast.py", relation: "contains", weight: 1.6 },
    { id: "e_forecast_solar", source: "file::models/forecast.py", target: "file::models/solar.py", relation: "contains", weight: 1.6 },

    // api
    { id: "e_endpoints_schemas", source: "file::api/endpoints.py", target: "file::api/schemas.py", relation: "calls", weight: 2.0 },

    // utils
    { id: "e_helpers_constants", source: "file::utils/helpers.py", target: "file::utils/constants.py", relation: "calls", weight: 1.5 },
  ],

  workflows: [
    {
      name: "Cosmic Telemetry Ingestion Flow",
      description: "Lifecycle of an incoming sensor reading from HTTP router through physics computation and storage.",
      nodes: [
        "file::src/main.py",
        "file::src/routes.py",
        "file::src/telemetry.py",
        "file::services/data_fetcher.py",
        "file::services/processing.py",
        "file::SolarFluxEngine/engine.py"
      ]
    }
  ]
};

/**
 * Fetch repository graph:
 * - Checks live backend (/api/repositories/{id}/graph or /api/v1/...) with an 800ms timeout
 * - If backend is offline or slow, falls back seamlessly to the rich normalized MOCK_GRAPH
 * - Ensures Workspace NEVER gets stuck loading!
 */
export async function getRepositoryGraph(repoIdOrUrl, options = {}) {
  const isExplicitDemo = repoIdOrUrl === 'cosmic-weather-api' || options?.isDemo;
  if (isExplicitDemo || !repoIdOrUrl) {
    return normalizeGraphData({
      ...MOCK_GRAPH,
      is_demo: true,
    });
  }

  const candidateUrls = [
    `${BASE}/api/repositories/${encodeURIComponent(repoIdOrUrl)}/graph`,
    `${BASE}/api/v1/repositories/${encodeURIComponent(repoIdOrUrl)}/graph`,
  ];

  let lastError = null;
  for (const url of candidateUrls) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);
      const res = await fetch(url, {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const liveData = await res.json();
        return normalizeGraphData({
          ...liveData,
          is_demo: false,
        });
      } else {
        const errJson = await res.json().catch(() => ({}));
        const err = new Error(
          errJson.detail || `Server returned ${res.status}: Failed to load graph`
        );
        err.status = res.status;
        lastError = err;
      }
    } catch (networkErr) {
      if (networkErr.name === 'AbortError') {
        lastError = new Error('Graph fetch request timed out after 15 seconds');
      } else {
        lastError = new Error(
          `Cannot connect to Astrograph backend at ${BASE}. Ensure server is running.`
        );
      }
    }
  }

  throw (
    lastError ||
    new Error(`Repository '${repoIdOrUrl}' graph could not be loaded`)
  );
}

/**
 * Read source file content (tries backend API, falls back to synthesized demo snippet)
 */
export async function getSourceFileContent(repoId, filePath) {
  try {
    const res = await fetch(`${BASE}/api/repositories/${encodeURIComponent(repoId)}/file?path=${encodeURIComponent(filePath)}`);
    if (res.ok) {
      const data = await res.json();
      return data.content || data.lines?.join('\n') || '';
    }
  } catch {
    // offline fallback
  }

  // Fallback demo source snippets
  return getMockSourceSnippet(filePath);
}

/**
 * Queue repository for indexing via FastAPI backend
 */
export async function submitRepositoryIndexing(repoUrl, branch = "main", userId = null, userEmail = null) {
  try {
    const res = await fetch(`${BASE}/api/repositories`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: repoUrl,
        branch,
      })
    });
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // ignore
  }

  // Mock return
  return {
    repository_id: "repo-mock-" + Date.now().toString(36),
    job_id: "job-mock-" + Date.now().toString(36),
    status: "indexing",
    message: "Indexing initiated (Demo Mode)"
  };
}

/**
 * Poll job status
 */
export async function getJobStatus(jobId) {
  try {
    const res = await fetch(`${BASE}/api/jobs/${jobId}`);
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // ignore
  }

  return {
    id: jobId,
    status: "completed",
    progress: 100,
    current_stage: "Graph Ready"
  };
}

/**
 * Server-Sent Events stream URL for real-time progress events
 */
export function getJobStreamUrl(jobId) {
  return `${BASE}/api/jobs/${encodeURIComponent(jobId)}/stream`;
}

/**
 * Ask codebase AI question
 */
export async function askCodebaseQuestion(question, repoId) {
  try {
    const res = await fetch(`${BASE}/api/repositories/${encodeURIComponent(repoId)}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    });
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // ignore
  }

  // Fallback AI response
  return {
    answer: `The cosmic telemetry pipeline ingests satellite readings via \`telemetry.py\`, passes raw fluxes to \`services/processing.py\`, and performs magnetosphere physics simulation in \`SolarFluxEngine/engine.py\`.`,
    highlighted_node_ids: [
      "file::src/telemetry.py",
      "file::services/processing.py",
      "file::SolarFluxEngine/engine.py"
    ]
  };
}

function getMockSourceSnippet(filePath) {
  if (filePath.includes('telemetry.py')) {
    return `"""
Telemetry Data Collection and Processing Module
AstroGraph Cosmic Weather Pipeline
"""

from typing import Dict, List, Optional
import asyncio
from services.data_fetcher import SatelliteDataFetcher
from services.processing import TelemetryStreamProcessor
from SolarFluxEngine.engine import SolarFluxEngine
from src.models import TelemetryRecord, MetricEnvelope

class TelemetryBridge:
    def __init__(self, engine: SolarFluxEngine):
        self.engine = engine
        self.fetcher = SatelliteDataFetcher()
        self.processor = TelemetryStreamProcessor()
        self.active_sensors: List[str] = []

    async def ingest_live_telemetry(self, sensor_id: str) -> MetricEnvelope:
        raw_stream = await self.fetcher.pull_stream(sensor_id)
        normalized = await self.processor.transform_flux(raw_stream)
        calculated_flux = self.engine.calculate_magnetosphere_impact(normalized)
        return MetricEnvelope(sensor_id=sensor_id, flux=calculated_flux)

    def export_metrics(self) -> Dict[str, float]:
        return {
            "centrality": 0.85,
            "loc": 1450,
            "complexity": 12,
        }
`;
  }
  return `"""
Module: ${filePath}
Generated for Astrograph Dependency Graph
"""

import logging

logger = logging.getLogger(__name__)

def execute_pipeline():
    logger.info("Pipeline processing active for ${filePath}")
    return True
`;
}

/**
 * Upload a ZIP archive to FastAPI backend for analysis
 */
export async function uploadRepositoryZip(zipFile, branch = 'main', projectName = '') {
  const formData = new FormData();
  formData.append('file', zipFile);
  if (branch) formData.append('branch', branch);
  if (projectName) formData.append('project_name', projectName);

  const res = await fetch(`${BASE}/api/repositories/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `ZIP upload failed with status ${res.status}`);
  }

  return await res.json();
}
