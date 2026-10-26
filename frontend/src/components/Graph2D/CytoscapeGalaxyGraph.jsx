import { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import cytoscape from 'cytoscape';
import {
  Search,
  SlidersHorizontal,
  Maximize2,
  ZoomIn,
  ZoomOut,
  Target,
  Folder,
  Layers,
  Share2,
  FileCode,
  Info,
  GitBranch,
  ArrowRight
} from 'lucide-react';
import GalaxyBackground2D from './GalaxyBackground2D.jsx';

// Inline SVG Data URIs for crisp logos inside node pills
const PYTHON_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><path fill="%23387eb8" d="M63.5 1.5c-30.8 0-28.8 13.3-28.8 13.3l.03 13.8h29.3v4.2H24.3C10.7 32.8 1.5 41.5 1.5 59.8c0 18.4 8 26.2 19.3 26.2h11.5v-16.1c0-12.2 10.5-22.9 22.9-22.9h29.2v-16.2c0-12.8-11.2-29.3-20.9-29.3zm-16.4 8.7c2.6 0 4.7 2.1 4.7 4.7s-2.1 4.7-4.7 4.7-4.7-2.1-4.7-4.7 2.1-4.7 4.7-4.7z"/><path fill="%23ffe052" d="M64.5 126.5c30.8 0 28.8-13.3 28.8-13.3l-.03-13.8H64v-4.2h39.7c13.6 0 22.8-8.7 22.8-27s-8-26.2-19.3-26.2H115.7v16.1c0 12.2-10.5 22.9-22.9 22.9H63.6v16.2c0 12.8 11.2 29.3 20.9 29.3zm16.4-8.7c-2.6 0-4.7-2.1-4.7-4.7s2.1-4.7 4.7-4.7 4.7 2.1 4.7 4.7-2.1 4.7-4.7 4.7z"/></svg>`;
const JS_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><rect width="128" height="128" rx="20" fill="%23f7df1e"/><path fill="%23000" d="M34.7 104.5c4.7 2.8 10.6 4.6 16.5 4.6 15.3 0 24.8-7.7 24.8-22.4V23.5h-16.2v63.1c0 7.8-4.3 11.7-11.5 11.7-5 0-9.2-1.7-12-3.4l-1.6 9.6zm51.4-1.2c5.9 3.6 14.1 6 22.6 6 18.2 0 28.3-9.5 28.3-24.1 0-13.7-8.2-20.9-20.9-26.7-9.5-4.2-13.5-7.7-13.5-13.1 0-4.8 3.8-8.5 10.9-8.5 6.4 0 12.1 2.2 16.3 4.9l4.3-10.8c-4.7-2.8-11.9-4.8-19.8-4.8-17.7 0-27.4 9.9-27.4 23.3 0 13.9 8.9 21.2 21.7 27 9.9 4.5 13.1 8.2 13.1 13.6 0 5.6-4.6 9.5-12.7 9.5-8.2 0-14.9-3.2-19.2-6.5l-3.8 10.2z"/></svg>`;
const CODE_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%2338bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>`;

// Preset cluster center points with generous spacing for the canonical reference demo (cosmic-weather-api)
const PRESET_CLUSTER_POSITIONS = {
  src: { x: -390, y: -230 },
  services: { x: 390, y: -240 },
  SolarFluxEngine: { x: -40, y: 270 },
  models: { x: -520, y: 270 },
  api: { x: 520, y: 50 },
  utils: { x: 450, y: 360 },
};

export default function CytoscapeGalaxyGraph({
  graphData,
  selectedNodeId,
  onSelectNode,
  onSelectCluster,
  className = '',
}) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const [clusterBoxes, setClusterBoxes] = useState([]);

  // Toolbar & Filter states
  const [searchQuery, setSearchQuery] = useState('');
  const [nodeTypeFilter, setNodeTypeFilter] = useState('file'); // Default to 'file' (matching Image 2 Desired Architecture)
  const [languageFilter, setLanguageFilter] = useState('all');
  const [dependencyFilter, setDependencyFilter] = useState('all'); // 'all' | 'imports' | 'calls' | 'defines' | 'contains' | 'cross'
  const [activeLayout, setActiveLayout] = useState('force'); // 'force' | 'hierarchical'
  const [viewMode, setViewMode] = useState('files'); // 'files' (File-level connections) | 'overview' (Directory Overview)

  // Floating hover tooltip state
  const [hoveredNode, setHoveredNode] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  // Available languages extracted dynamically from graph
  const availableLanguages = useMemo(() => {
    if (!graphData?.nodes) return ['all'];
    const langs = new Set(graphData.nodes.map((n) => n.language).filter(Boolean));
    return ['all', ...Array.from(langs)];
  }, [graphData]);

  // Compute Cytoscape elements (File child nodes + Direct File-to-File edges)
  const elements = useMemo(() => {
    if (!graphData || !Array.isArray(graphData.nodes)) return [];

    const elems = [];
    const activeNodeIds = new Set();
    const nodeMap = new Map();
    graphData.nodes.forEach((n) => nodeMap.set(n.id, n));

    // Determine available files vs symbols
    const fileNodes = graphData.nodes.filter((n) => n.type === 'file');
    const effectiveTypeFilter = nodeTypeFilter === 'file' && fileNodes.length === 0 ? 'all' : nodeTypeFilter;

    // 1. Filter nodes based on toolbar controls
    const validNodes = graphData.nodes.filter((node) => {
      // Search query filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesLabel = node.label?.toLowerCase().includes(q);
        const matchesPath = node.path?.toLowerCase().includes(q);
        const matchesCluster = node.cluster?.toLowerCase().includes(q);
        if (!matchesLabel && !matchesPath && !matchesCluster) return false;
      }

      // Node type filter (Files only by default as requested in Image 2)
      if (effectiveTypeFilter !== 'all') {
        if (effectiveTypeFilter === 'file' && node.type !== 'file') return false;
        if (effectiveTypeFilter === 'symbol' && node.type === 'file') return false;
      }

      // Language filter
      if (languageFilter !== 'all' && node.language && node.language.toLowerCase() !== languageFilter.toLowerCase()) {
        return false;
      }

      return true;
    });

    validNodes.forEach((n) => activeNodeIds.add(n.id));

    // 2. Add Nodes with dynamic width & appropriate language icon
    validNodes.forEach((node) => {
      let icon = CODE_SVG;
      const lang = (node.language || '').toLowerCase();
      const ext = (node.path || '').split('.').pop()?.toLowerCase();
      if (lang === 'python' || ext === 'py') icon = PYTHON_SVG;
      else if (lang === 'javascript' || lang === 'typescript' || ext === 'js' || ext === 'jsx' || ext === 'ts' || ext === 'tsx') icon = JS_SVG;

      const labelText = node.label || node.name || 'node';
      const nodeWidth = Math.max(160, Math.min(240, labelText.length * 8.8 + 48));

      elems.push({
        group: 'nodes',
        data: {
          id: node.id,
          label: labelText,
          path: node.path,
          cluster: node.cluster,
          type: node.type,
          language: node.language || (ext === 'py' ? 'python' : 'javascript'),
          loc: node.metrics?.loc || 0,
          centrality: node.metrics?.centrality || 0,
          complexity: node.metrics?.complexity || 0,
          ai_summary: node.ai_summary,
          width: nodeWidth,
          icon,
        },
      });
    });

    // 3. Add Direct File-to-File Edges (or rolled-up file dependencies when in file mode)
    if (Array.isArray(graphData.edges)) {
      const edgeKeySet = new Set();

      graphData.edges.forEach((edge) => {
        let src = edge.source;
        let tgt = edge.target;

        // In 'file' view mode, if an edge was between AST symbols within files, roll up to enclosing files!
        if (effectiveTypeFilter === 'file') {
          if (!activeNodeIds.has(src) && edge.sourceFileId && activeNodeIds.has(edge.sourceFileId)) {
            src = edge.sourceFileId;
          }
          if (!activeNodeIds.has(tgt) && edge.targetFileId && activeNodeIds.has(edge.targetFileId)) {
            tgt = edge.targetFileId;
          }
        }

        if (!activeNodeIds.has(src) || !activeNodeIds.has(tgt) || src === tgt) return;

        // Dependency relation filter
        if (dependencyFilter !== 'all') {
          if (dependencyFilter === 'cross' && !edge.is_cross_cluster) return;
          if (dependencyFilter !== 'cross' && edge.relation !== dependencyFilter) return;
        }

        const relation = edge.relation || 'imports';
        const edgeDedupeKey = `${src}->${tgt}::${relation}`;
        if (edgeKeySet.has(edgeDedupeKey)) return;
        edgeKeySet.add(edgeDedupeKey);

        elems.push({
          group: 'edges',
          data: {
            id: `cy-edge-${src}-${tgt}-${relation}`,
            source: src,
            target: tgt,
            relation,
            weight: edge.weight || 1.0,
            is_cross_cluster: edge.is_cross_cluster,
          },
        });
      });
    }

    return elems;
  }, [graphData, searchQuery, nodeTypeFilter, languageFilter, dependencyFilter]);

  // Synchronize dynamic visual cluster container boxes based on rendered node bounding boxes
  const updateClusterBoxes = useCallback(() => {
    const cy = cyRef.current;
    if (!cy || !graphData?.clusters) return;

    const boxes = [];
    graphData.clusters.forEach((cluster) => {
      const nodesInCluster = cy.nodes(`[cluster = "${cluster.path}"]`);
      if (nodesInCluster.length === 0) return;

      const rbb = nodesInCluster.renderedBoundingBox();
      if (!rbb || rbb.w <= 0 || rbb.h <= 0) return;

      // Ample padding around child nodes so pills never touch borders or header
      const padX = 36;
      const padTop = 56;
      const padBottom = 30;

      boxes.push({
        id: cluster.id,
        path: cluster.path,
        name: cluster.name,
        color: cluster.color,
        bg: cluster.bg,
        textColor: cluster.textColor || '#fff',
        count: nodesInCluster.length,
        x: rbb.x1 - padX,
        y: rbb.y1 - padTop,
        width: rbb.w + padX * 2,
        height: rbb.h + padTop + padBottom,
      });
    });

    setClusterBoxes(boxes);
  }, [graphData]);

  // Apply Cytoscape Layout with Spacious, Collision-Free Positioning
  const applyLayout = useCallback((layoutType = activeLayout) => {
    const cy = cyRef.current;
    if (!cy) return;

    const clusters = graphData?.clusters || [];
    const isDemoRepo = graphData?.is_demo || graphData?.repo_name === 'cosmic-weather-api';

    if (layoutType === 'force') {
      // ─── 1. MODULAR FORCE / SPACIOUS ARCHITECTURAL LAYOUT ──────────────────
      // Dynamic collision-free layout for ANY repository:
      // Clusters are arranged across spacious 2D canvas coordinates without overlapping.
      // Inside each cluster, nodes are arranged in a wide, comfortable multi-column grid.

      // Pre-calculate dimensions for each cluster to position them with zero collisions
      const clusterDimensions = {};
      clusters.forEach((cluster) => {
        const childNodes = cy.nodes(`[cluster = "${cluster.path}"]`);
        const count = childNodes.length;
        // Adaptive multi-column grid
        const cols = count <= 1 ? 1 : count <= 4 ? 2 : count <= 9 ? 3 : count <= 16 ? 4 : 5;
        const rows = Math.ceil(count / cols);
        const stepX = 210;
        const stepY = 64;
        const width = (cols - 1) * stepX + 175 + 80;
        const height = (rows - 1) * stepY + 38 + 95;
        clusterDimensions[cluster.path] = { count, cols, rows, stepX, stepY, width, height };
      });

      // Calculate cluster center positions
      const clusterCenters = {};
      if (isDemoRepo) {
        // Use carefully balanced positions matching Image 2 reference design
        clusters.forEach((c) => {
          clusterCenters[c.path] = PRESET_CLUSTER_POSITIONS[c.path] || { x: 0, y: 0 };
        });
      } else {
        // Generic dynamic collision-free grid packing for any real codebase (makemore, express, etc.)
        let currentX = 0;
        let currentY = 0;
        let maxHeightInRow = 0;
        const MAX_ROW_WIDTH = 1600;
        const CLUSTER_MARGIN_X = 140;
        const CLUSTER_MARGIN_Y = 140;

        const sortedClusters = [...clusters].sort((a, b) => {
          const countA = cy.nodes(`[cluster = "${a.path}"]`).length;
          const countB = cy.nodes(`[cluster = "${b.path}"]`).length;
          return countB - countA;
        });

        const placedBoxes = [];
        sortedClusters.forEach((cluster) => {
          const dim = clusterDimensions[cluster.path];
          if (!dim || dim.count === 0) return;

          if (currentX + dim.width > MAX_ROW_WIDTH && placedBoxes.length > 0) {
            currentX = 0;
            currentY += maxHeightInRow + CLUSTER_MARGIN_Y;
            maxHeightInRow = 0;
          }

          clusterCenters[cluster.path] = {
            x: currentX + dim.width / 2,
            y: currentY + dim.height / 2,
          };

          placedBoxes.push({
            path: cluster.path,
            x: currentX,
            y: currentY,
            width: dim.width,
            height: dim.height,
          });

          maxHeightInRow = Math.max(maxHeightInRow, dim.height);
          currentX += dim.width + CLUSTER_MARGIN_X;
        });

        // Center all clusters around canvas origin (0, 0)
        if (placedBoxes.length > 0) {
          const minX = Math.min(...placedBoxes.map((b) => b.x));
          const maxX = Math.max(...placedBoxes.map((b) => b.x + b.width));
          const minY = Math.min(...placedBoxes.map((b) => b.y));
          const maxY = Math.max(...placedBoxes.map((b) => b.y + b.height));
          const midX = (minX + maxX) / 2;
          const midY = (minY + maxY) / 2;

          Object.keys(clusterCenters).forEach((k) => {
            clusterCenters[k].x -= midX;
            clusterCenters[k].y -= midY;
          });
        }
      }

      // Position individual nodes inside their respective clusters
      clusters.forEach((cluster) => {
        const basePos = clusterCenters[cluster.path] || { x: 0, y: 0 };
        const childNodes = cy.nodes(`[cluster = "${cluster.path}"]`);
        const dim = clusterDimensions[cluster.path] || { cols: 2, stepX: 210, stepY: 64 };

        childNodes.forEach((child, idx) => {
          let offsetX = 0;
          let offsetY = 0;

          if (isDemoRepo && cluster.path === 'src') {
            const srcOffsets = [
              { x: -30, y: -70 },  // main.py
              { x: -110, y: -10 }, // routes.py
              { x: 65, y: -10 },   // telemetry.py
              { x: -90, y: 65 },   // models.py
              { x: 55, y: 65 },    // weather.py
            ];
            offsetX = srcOffsets[idx]?.x ?? 0;
            offsetY = srcOffsets[idx]?.y ?? 0;
          } else if (isDemoRepo && cluster.path === 'services') {
            const servOffsets = [
              { x: 65, y: -60 },   // data_fetcher.py
              { x: -75, y: 0 },    // processing.py
              { x: 80, y: 35 },    // api_client.py
            ];
            offsetX = servOffsets[idx]?.x ?? 0;
            offsetY = servOffsets[idx]?.y ?? 0;
          } else if (isDemoRepo && cluster.path === 'SolarFluxEngine') {
            const solarOffsets = [
              { x: 0, y: -70 },    // engine.py
              { x: -95, y: 0 },    // magnetosphere.py
              { x: 85, y: 0 },     // solar.py
              { x: 0, y: 65 },     // prediction.py
            ];
            offsetX = solarOffsets[idx]?.x ?? 0;
            offsetY = solarOffsets[idx]?.y ?? 0;
          } else if (isDemoRepo && cluster.path === 'models') {
            const modOffsets = [
              { x: 0, y: -55 },    // base.py
              { x: -75, y: 20 },   // forecast.py
              { x: 65, y: 40 },    // solar.py
            ];
            offsetX = modOffsets[idx]?.x ?? 0;
            offsetY = modOffsets[idx]?.y ?? 0;
          } else if (isDemoRepo && cluster.path === 'api') {
            const apiOffsets = [
              { x: 0, y: -35 },    // endpoints.py
              { x: 5, y: 35 },     // schemas.py
            ];
            offsetX = apiOffsets[idx]?.x ?? 0;
            offsetY = apiOffsets[idx]?.y ?? 0;
          } else if (isDemoRepo && cluster.path === 'utils') {
            const utilOffsets = [
              { x: -10, y: -30 },   // helpers.py
              { x: 35, y: 30 },     // constants.py
            ];
            offsetX = utilOffsets[idx]?.x ?? 0;
            offsetY = utilOffsets[idx]?.y ?? 0;
          } else {
            // Adaptive multi-column grid with generous spacing
            const cols = dim.cols || 3;
            const col = idx % cols;
            const row = Math.floor(idx / cols);
            const totalW = (cols - 1) * dim.stepX;
            const totalH = (dim.rows - 1) * dim.stepY;
            offsetX = col * dim.stepX - totalW / 2;
            offsetY = row * dim.stepY - totalH / 2 + 10;
          }

          child.position({
            x: basePos.x + offsetX,
            y: basePos.y + offsetY,
          });
        });
      });

      // Clamp initial zoom so labels are crisp and readable without having to zoom in
      cy.fit(undefined, 80);
      const zoom = cy.zoom();
      if (zoom < 0.85) {
        cy.zoom(0.88);
        cy.center();
      }
      setTimeout(updateClusterBoxes, 50);
    } else if (layoutType === 'hierarchical') {
      // ─── 2. HIERARCHICAL PIPELINE LAYOUT ──────────────────────────────────
      // Groups clusters into clean architectural tiers from top to bottom
      const clustersList = graphData?.clusters || [];
      const edges = graphData?.edges || [];

      const clusterInDegree = {};
      const clusterOut = {};
      clustersList.forEach((c) => {
        clusterInDegree[c.path] = 0;
        clusterOut[c.path] = new Set();
      });

      edges.forEach((e) => {
        const sNode = graphData.nodes?.find((n) => n.id === e.source);
        const tNode = graphData.nodes?.find((n) => n.id === e.target);
        if (sNode && tNode && sNode.cluster !== tNode.cluster) {
          if (clusterOut[sNode.cluster]) {
            clusterOut[sNode.cluster].add(tNode.cluster);
          }
        }
      });

      Object.keys(clusterOut).forEach((sc) => {
        clusterOut[sc].forEach((tc) => {
          if (clusterInDegree[tc] !== undefined) {
            clusterInDegree[tc] = (clusterInDegree[tc] || 0) + 1;
          }
        });
      });

      const clusterLevels = {};
      const roots = Object.keys(clusterInDegree).filter((c) => clusterInDegree[c] === 0);
      roots.forEach((c) => { clusterLevels[c] = 0; });

      const queue = [...roots];
      const remainingIn = { ...clusterInDegree };
      while (queue.length > 0) {
        const curr = queue.shift();
        const currLvl = clusterLevels[curr] || 0;
        if (clusterOut[curr]) {
          clusterOut[curr].forEach((neighbor) => {
            clusterLevels[neighbor] = Math.max(clusterLevels[neighbor] || 0, currLvl + 1);
            if (remainingIn[neighbor] !== undefined) {
              remainingIn[neighbor]--;
              if (remainingIn[neighbor] <= 0) {
                queue.push(neighbor);
              }
            }
          });
        }
      }

      clustersList.forEach((c) => {
        if (clusterLevels[c.path] === undefined) {
          clusterLevels[c.path] = 1;
        }
      });

      const tiers = {};
      clustersList.forEach((c) => {
        const lvl = clusterLevels[c.path] || 0;
        if (!tiers[lvl]) tiers[lvl] = [];
        tiers[lvl].push(c);
      });

      const TIER_HEIGHT = 420;
      const CLUSTER_WIDTH = 480;
      const tierKeys = Object.keys(tiers).map(Number).sort((a, b) => a - b);

      tierKeys.forEach((lvl) => {
        const clustersInTier = tiers[lvl];
        const tierY = (lvl - (tierKeys.length - 1) / 2) * TIER_HEIGHT;
        const totalW = (clustersInTier.length - 1) * CLUSTER_WIDTH;

        clustersInTier.forEach((cluster, colIdx) => {
          const clusterX = colIdx * CLUSTER_WIDTH - totalW / 2;
          const childNodes = cy.nodes(`[cluster = "${cluster.path}"]`);

          const count = childNodes.length;
          const cols = count <= 2 ? 1 : count <= 6 ? 2 : 3;
          const rows = Math.ceil(count / cols);
          const stepX = 210;
          const stepY = 64;

          childNodes.forEach((child, idx) => {
            const col = idx % cols;
            const row = Math.floor(idx / cols);
            const offsetX = col * stepX - ((cols - 1) * stepX) / 2;
            const offsetY = row * stepY - ((rows - 1) * stepY) / 2 + 10;

            child.position({
              x: clusterX + offsetX,
              y: tierY + offsetY,
            });
          });
        });
      });

      cy.fit(undefined, 90);
      const zoom = cy.zoom();
      if (zoom < 0.85) {
        cy.zoom(0.88);
        cy.center();
      }
      setTimeout(updateClusterBoxes, 50);
    }
  }, [activeLayout, graphData, updateClusterBoxes]);

  // Initialize Cytoscape Instance
  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      boxSelectionEnabled: false,
      autounselectify: false,
      wheelSensitivity: 0.25,
      minZoom: 0.25,
      maxZoom: 3.5,
      style: [
        // ─── FILE NODES (Pills matching Image 2 reference design) ────────────
        {
          selector: 'node',
          style: {
            'shape': 'round-rectangle',
            'width': 'data(width)',
            'height': 38,
            'corner-radius': 12,
            'background-color': '#080e1e',
            'background-opacity': 0.98,
            'border-width': 1.8,
            'border-color': '#38bdf8', // Glowing cyan default
            'border-opacity': 0.9,
            'label': 'data(label)',
            'color': '#f8fafc',
            'text-valign': 'center',
            'text-halign': 'center',
            'font-family': "'JetBrains Mono', 'Plus Jakarta Sans', monospace",
            'font-size': '12px',
            'font-weight': 600,
            'background-image': 'data(icon)',
            'background-fit': 'contain',
            'background-width': '16px',
            'background-height': '16px',
            'background-position-x': '13px',
            'background-position-y': '50%',
            'text-margin-x': '10px',
            'text-outline-color': '#080e1e',
            'text-outline-width': 2,
            'cursor': 'pointer',
            'transition-property': 'border-color, border-width, opacity, underlay-opacity',
            'transition-duration': '0.2s',
            'z-index': 10,
          },
        },
        // ─── DIRECTED DEPENDENCY EDGES ───────────────────────────────────────
        {
          selector: 'edge',
          style: {
            'width': 2.0,
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 1.2,
            'line-opacity': 0.7,
            'target-arrow-fill': 'filled',
            'transition-property': 'line-color, width, line-opacity, z-index',
            'transition-duration': '0.2s',
            'z-index': 5,
          },
        },
        // Edge color variations matching Image 2 Legend
        {
          selector: 'edge[relation = "imports"]',
          style: {
            'line-color': '#f97316', // Orange
            'target-arrow-color': '#f97316',
          },
        },
        {
          selector: 'edge[relation = "calls"]',
          style: {
            'line-color': '#38bdf8', // Cyan/Blue
            'target-arrow-color': '#38bdf8',
          },
        },
        {
          selector: 'edge[relation = "defines"]',
          style: {
            'line-color': '#a855f7', // Purple
            'target-arrow-color': '#a855f7',
          },
        },
        {
          selector: 'edge[relation = "contains"]',
          style: {
            'line-color': '#10b981', // Emerald Green
            'target-arrow-color': '#10b981',
          },
        },

        // ─── SELECTION & FOCUS HIGHLIGHTING ──────────────────────────────────
        {
          selector: 'node.selected',
          style: {
            'border-color': '#f43f5e', // Neon rose/pink border
            'border-width': 3.0,
            'border-opacity': 1.0,
            'background-color': '#1a1028',
            'underlay-color': '#f43f5e',
            'underlay-padding': 8,
            'underlay-opacity': 0.45,
            'underlay-shape': 'round-rectangle',
            'z-index': 99,
          },
        },
        {
          selector: 'node.connected-neighbor',
          style: {
            'border-color': '#38bdf8',
            'border-width': 2.4,
            'border-opacity': 1.0,
            'opacity': 1.0,
            'z-index': 80,
          },
        },
        {
          selector: 'edge.highlighted-edge',
          style: {
            'width': 3.2,
            'line-opacity': 1.0,
            'target-arrow-fill': 'filled',
            'arrow-scale': 1.4,
            'z-index': 90,
          },
        },
        {
          selector: '.dimmed',
          style: {
            'opacity': 0.15,
          },
        },
        {
          selector: 'node:active',
          style: {
            'overlay-opacity': 0,
          },
        },
      ],
    });

    cyRef.current = cy;

    // Synchronize cluster boxes on pan, zoom, render, or drag
    cy.on('render pan zoom position drag', () => {
      updateClusterBoxes();
    });

    // Node click handler
    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      onSelectNode?.(node.id());
    });

    // Node hover tooltip handlers
    cy.on('mouseover', 'node', (evt) => {
      const node = evt.target;
      const renderedPos = node.renderedPosition();
      setHoveredNode(node.data());
      setTooltipPos({ x: renderedPos.x, y: renderedPos.y });
    });

    cy.on('mouseout', 'node', () => {
      setHoveredNode(null);
    });

    // Background click (deselect)
    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        onSelectNode?.(null);
      }
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, []);

  // Update elements on change
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.elements().remove();
    cy.add(elements);
    applyLayout(activeLayout);
  }, [elements, graphData]);

  // Synchronize selection state with Cytoscape styling
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.elements().removeClass('selected connected-neighbor highlighted-edge dimmed');

    if (!selectedNodeId) {
      return;
    }

    const selectedNode = cy.getElementById(selectedNodeId);
    if (!selectedNode || selectedNode.length === 0) return;

    // Dim all elements first
    cy.elements().addClass('dimmed');

    // Highlight selected node
    selectedNode.removeClass('dimmed').addClass('selected');

    // Find incoming and outgoing edges
    const connectedEdges = selectedNode.connectedEdges();
    connectedEdges.removeClass('dimmed').addClass('highlighted-edge');

    // Find directly connected neighbor nodes
    const connectedNodes = connectedEdges.connectedNodes();
    connectedNodes.removeClass('dimmed').addClass('connected-neighbor');
  }, [selectedNodeId]);

  // Center on selected node when triggered
  const handleCenterOnSelected = () => {
    const cy = cyRef.current;
    if (!cy) return;
    if (selectedNodeId) {
      const target = cy.getElementById(selectedNodeId);
      if (target.length > 0) {
        cy.animate({
          center: { eles: target },
          zoom: 1.15,
          duration: 400,
        });
        return;
      }
    }
    cy.fit(undefined, 80);
    if (cy.zoom() < 0.85) {
      cy.zoom(0.88);
      cy.center();
    }
  };

  // Keyboard shortcut listener (Cmd+K / Ctrl+K)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        const searchInput = document.getElementById('astro-graph-search-input');
        searchInput?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <div
      className={`graph2d-container ${className}`}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: '#050813',
      }}
    >
      {/* ─── TOP FILTER & SEARCH TOOLBAR ───────────────────────────────────── */}
      <div
        style={{
          position: 'relative',
          zIndex: 30,
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '0.75rem',
          padding: '0.65rem 1.25rem',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          background: 'rgba(7, 11, 22, 0.92)',
          backdropFilter: 'blur(16px)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1, minWidth: '320px' }}>
          {/* Search Input */}
          <div style={{ position: 'relative', flex: 1, maxWidth: '380px' }}>
            <Search
              size={14}
              style={{
                position: 'absolute',
                left: '12px',
                top: '50%',
                transform: 'translateY(-50%)',
                color: '#64748b',
                pointerEvents: 'none',
              }}
            />
            <input
              id="astro-graph-search-input"
              type="text"
              style={{
                width: '100%',
                backgroundColor: '#0d1424',
                color: '#ffffff',
                fontSize: '0.78rem',
                paddingLeft: '34px',
                paddingRight: '50px',
                paddingTop: '7px',
                paddingBottom: '7px',
                borderRadius: '8px',
                border: '1px solid rgba(255, 255, 255, 0.12)',
                outline: 'none',
                fontFamily: 'var(--font-mono, monospace)',
                boxSizing: 'border-box',
              }}
              placeholder="Search files, symbols, folders..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <span
              style={{
                position: 'absolute',
                right: '10px',
                top: '50%',
                transform: 'translateY(-50%)',
                fontSize: '10px',
                color: '#64748b',
                backgroundColor: 'rgba(255, 255, 255, 0.06)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                padding: '2px 5px',
                borderRadius: '4px',
                fontFamily: 'monospace',
                pointerEvents: 'none',
              }}
            >
              ⌘ K
            </span>
          </div>

          {/* Node Type Filter (Files only default as requested in Image 2) */}
          <select
            style={{
              backgroundColor: '#0d1424',
              color: '#38bdf8',
              fontWeight: 600,
              fontSize: '0.75rem',
              padding: '6px 12px',
              borderRadius: '8px',
              border: '1px solid rgba(56, 189, 248, 0.3)',
              outline: 'none',
              cursor: 'pointer',
            }}
            value={nodeTypeFilter}
            onChange={(e) => setNodeTypeFilter(e.target.value)}
          >
            <option value="file">Files only (Architecture)</option>
            <option value="all">All nodes (Files & Symbols)</option>
            <option value="symbol">Symbols only</option>
          </select>

          {/* Language Filter */}
          <select
            style={{
              backgroundColor: '#0d1424',
              color: '#d1d5db',
              fontSize: '0.75rem',
              padding: '6px 10px',
              borderRadius: '8px',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              outline: 'none',
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
            value={languageFilter}
            onChange={(e) => setLanguageFilter(e.target.value)}
          >
            {availableLanguages.map((lang) => (
              <option key={lang} value={lang}>
                {lang === 'all' ? 'All languages' : lang.toUpperCase()}
              </option>
            ))}
          </select>

          {/* Dependency Filter */}
          <select
            style={{
              backgroundColor: '#0d1424',
              color: '#d1d5db',
              fontSize: '0.75rem',
              padding: '6px 10px',
              borderRadius: '8px',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              outline: 'none',
              cursor: 'pointer',
            }}
            value={dependencyFilter}
            onChange={(e) => setDependencyFilter(e.target.value)}
          >
            <option value="all">All dependencies</option>
            <option value="imports">Imports only (Orange)</option>
            <option value="calls">Function calls (Cyan)</option>
            <option value="defines">Defines (Purple)</option>
            <option value="contains">Contains / Uses (Green)</option>
            <option value="cross">Cross-folder only</option>
          </select>
        </div>

        {/* Layout & Mode Toggle Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button
            type="button"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              fontSize: '0.75rem',
              fontWeight: 600,
              borderRadius: '8px',
              border: activeLayout === 'force' ? '1px solid #38bdf8' : '1px solid rgba(255, 255, 255, 0.1)',
              backgroundColor: activeLayout === 'force' ? 'rgba(56, 189, 248, 0.15)' : 'rgba(255, 255, 255, 0.05)',
              color: activeLayout === 'force' ? '#38bdf8' : '#9ca3af',
              boxShadow: activeLayout === 'force' ? '0 0 12px rgba(56, 189, 248, 0.25)' : 'none',
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
            onClick={() => {
              setActiveLayout('force');
              applyLayout('force');
            }}
          >
            <Share2 size={13} />
            <span>Modular Force</span>
          </button>

          <button
            type="button"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              fontSize: '0.75rem',
              fontWeight: 600,
              borderRadius: '8px',
              border: activeLayout === 'hierarchical' ? '1px solid #38bdf8' : '1px solid rgba(255, 255, 255, 0.1)',
              backgroundColor: activeLayout === 'hierarchical' ? 'rgba(56, 189, 248, 0.15)' : 'rgba(255, 255, 255, 0.05)',
              color: activeLayout === 'hierarchical' ? '#38bdf8' : '#9ca3af',
              boxShadow: activeLayout === 'hierarchical' ? '0 0 12px rgba(56, 189, 248, 0.25)' : 'none',
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
            onClick={() => {
              setActiveLayout('hierarchical');
              applyLayout('hierarchical');
            }}
          >
            <Layers size={13} />
            <span>Hierarchical</span>
          </button>

          <button
            type="button"
            style={{
              padding: '7px',
              borderRadius: '8px',
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: '#9ca3af',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Reset Filters"
            onClick={() => {
              setSearchQuery('');
              setNodeTypeFilter('file');
              setLanguageFilter('all');
              setDependencyFilter('all');
            }}
          >
            <SlidersHorizontal size={14} />
          </button>
        </div>
      </div>

      {/* ─── MAIN CYTOSCAPE CANVAS AREA ────────────────────────────────────── */}
      <div
        style={{
          position: 'relative',
          flex: 1,
          width: '100%',
          height: '100%',
          overflow: 'hidden',
        }}
      >
        {/* Cinematic deep space starry background */}
        <GalaxyBackground2D />

        {/* ─── VISUAL CLUSTER CONTAINERS (BEHIND NODES & EDGES) ─────────────── */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            pointerEvents: 'none',
            zIndex: 2,
            overflow: 'hidden',
          }}
        >
          {clusterBoxes.map((box) => (
            <div
              key={box.id}
              style={{
                position: 'absolute',
                left: `${box.x}px`,
                top: `${box.y}px`,
                width: `${box.width}px`,
                height: `${box.height}px`,
                backgroundColor: box.bg,
                border: `2px solid ${box.color}`,
                borderRadius: '20px',
                boxShadow: `0 8px 32px rgba(0, 0, 0, 0.45), inset 0 0 20px ${box.color}15`,
                pointerEvents: 'auto',
                cursor: 'pointer',
                transition: 'border-color 0.2s, background-color 0.2s, box-shadow 0.2s',
                zIndex: 2,
              }}
              onClick={(e) => {
                e.stopPropagation();
                onSelectCluster?.({
                  id: box.id,
                  path: box.path,
                  name: box.name,
                  color: box.color,
                });
              }}
            >
              {/* Cluster Header matching Image 2: folder icon + name on left, file count badge on right */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px 18px',
                  userSelect: 'none',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Folder size={16} style={{ color: box.color }} />
                  <span
                    style={{
                      fontFamily: "'JetBrains Mono', 'Plus Jakarta Sans', monospace",
                      fontSize: '13px',
                      fontWeight: 700,
                      color: box.color,
                      letterSpacing: '0.02em',
                    }}
                  >
                    {box.name}
                  </span>
                </div>

                <div
                  style={{
                    fontSize: '11px',
                    fontFamily: "'JetBrains Mono', monospace",
                    fontWeight: 600,
                    padding: '3px 10px',
                    borderRadius: '9999px',
                    backgroundColor: 'rgba(0, 0, 0, 0.55)',
                    border: `1px solid ${box.color}66`,
                    color: '#e2e8f0',
                  }}
                >
                  {box.count} {box.count === 1 ? 'file' : 'files'}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Cytoscape DOM container (File nodes + File-to-file arrows) */}
        <div
          ref={containerRef}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            zIndex: 10,
          }}
        />

        {/* ─── FLOATING HOVER TOOLTIP HUD ──────────────────────────────────── */}
        {hoveredNode && (
          <div
            style={{
              position: 'absolute',
              left: `${Math.min(window.innerWidth - 280, Math.max(20, tooltipPos.x + 20))}px`,
              top: `${Math.min(window.innerHeight - 200, Math.max(20, tooltipPos.y - 40))}px`,
              zIndex: 40,
              pointerEvents: 'none',
              backgroundColor: 'rgba(9, 14, 28, 0.94)',
              border: '1px solid #38bdf8',
              borderRadius: '12px',
              padding: '10px 14px',
              boxShadow: '0 12px 30px rgba(0, 0, 0, 0.6), 0 0 15px rgba(56, 189, 248, 0.2)',
              backdropFilter: 'blur(16px)',
              minWidth: '220px',
              maxWidth: '320px',
              animation: 'fadeIn 0.15s ease-out',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <FileCode size={14} style={{ color: '#38bdf8' }} />
                <span style={{ fontWeight: 700, fontSize: '13px', color: '#f8fafc', fontFamily: 'var(--font-mono)' }}>
                  {hoveredNode.label}
                </span>
              </div>
              <span
                style={{
                  fontSize: '10px',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(56, 189, 248, 0.15)',
                  color: '#38bdf8',
                  textTransform: 'uppercase',
                  fontWeight: 600,
                }}
              >
                {hoveredNode.type}
              </span>
            </div>

            <div style={{ fontSize: '11px', color: '#94a3b8', fontFamily: 'monospace', marginBottom: '6px', wordBreak: 'break-all' }}>
              📁 {hoveredNode.path}
            </div>

            <div style={{ display: 'flex', gap: '12px', fontSize: '11px', color: '#cbd5e1', paddingTop: '6px', borderTop: '1px solid rgba(255, 255, 255, 0.1)' }}>
              <span>LOC: <strong style={{ color: '#f8fafc' }}>{hoveredNode.loc}</strong></span>
              <span>Centrality: <strong style={{ color: '#38bdf8' }}>{Math.round((hoveredNode.centrality || 0) * 100)}%</strong></span>
            </div>
          </div>
        )}

        {/* ─── FLOATING BOTTOM-LEFT CONTROLS ───────────────────────────────── */}
        <div
          style={{
            position: 'absolute',
            bottom: '24px',
            left: '24px',
            zIndex: 25,
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            padding: '4px',
            borderRadius: '12px',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            background: 'rgba(10, 16, 30, 0.92)',
            backdropFilter: 'blur(12px)',
            boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)',
          }}
        >
          <button
            type="button"
            style={{
              padding: '6px 8px',
              borderRadius: '8px',
              color: '#d1d5db',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Zoom In"
            onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 1.25)}
          >
            <ZoomIn size={15} />
          </button>
          <button
            type="button"
            style={{
              padding: '6px 8px',
              borderRadius: '8px',
              color: '#d1d5db',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Zoom Out"
            onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 0.8)}
          >
            <ZoomOut size={15} />
          </button>
          <button
            type="button"
            style={{
              padding: '6px 8px',
              borderRadius: '8px',
              color: '#d1d5db',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Fit to Screen"
            onClick={handleCenterOnSelected}
          >
            <Maximize2 size={15} />
          </button>
          <button
            type="button"
            style={{
              padding: '6px 8px',
              borderRadius: '8px',
              color: '#d1d5db',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Center on Node"
            onClick={handleCenterOnSelected}
          >
            <Target size={15} />
          </button>
          <div style={{ width: '1px', height: '18px', backgroundColor: 'rgba(255, 255, 255, 0.1)', margin: '0 4px' }} />
          <span style={{ fontSize: '11px', fontFamily: 'monospace', padding: '0 8px', color: '#38bdf8', textTransform: 'capitalize' }}>
            {activeLayout === 'force' ? 'Modular Force' : 'Hierarchical'}
          </span>
        </div>

        {/* ─── BOTTOM GRAPH LEGEND MATCHING IMAGE 2 EXACTLY ─────────────────── */}
        <div
          style={{
            position: 'absolute',
            bottom: '24px',
            right: '24px',
            zIndex: 25,
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: '14px',
            padding: '8px 18px',
            borderRadius: '12px',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            background: 'rgba(10, 16, 30, 0.90)',
            backdropFilter: 'blur(14px)',
            fontSize: '11px',
            fontFamily: 'var(--font-mono, monospace)',
          }}
        >
          {/* Node Types */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '12px', height: '12px', borderRadius: '3px', backgroundColor: 'rgba(244, 63, 94, 0.25)', border: '1.2px solid #f43f5e', display: 'inline-block' }} />
            <span style={{ color: '#d1d5db' }}>Directory (cluster)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '16px', height: '8px', borderRadius: '3px', backgroundColor: '#080e1e', border: '1.2px solid #38bdf8', display: 'inline-block' }} />
            <span style={{ color: '#d1d5db' }}>File (node)</span>
          </div>

          <div style={{ width: '1px', height: '14px', backgroundColor: 'rgba(255, 255, 255, 0.15)' }} />

          {/* Edge Types matching Image 2 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '14px', height: '2.5px', backgroundColor: '#f97316', display: 'inline-block' }} />
            <span style={{ color: '#f97316', fontWeight: 600 }}>IMPORTS</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '14px', height: '2.5px', backgroundColor: '#38bdf8', display: 'inline-block' }} />
            <span style={{ color: '#38bdf8', fontWeight: 600 }}>CALLS</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '14px', height: '2.5px', backgroundColor: '#10b981', display: 'inline-block' }} />
            <span style={{ color: '#10b981', fontWeight: 600 }}>CONTAINS</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '14px', height: '2.5px', backgroundColor: '#a855f7', display: 'inline-block' }} />
            <span style={{ color: '#a855f7', fontWeight: 600 }}>DEFINES</span>
          </div>

          <div style={{ width: '1px', height: '14px', backgroundColor: 'rgba(255, 255, 255, 0.15)' }} />

          <span style={{ color: '#64748b', fontSize: '10.5px' }}>
            Pan: Drag • Zoom: Scroll • Select: Click
          </span>
        </div>
      </div>
    </div>
  );
}
