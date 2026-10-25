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
  Share2
} from 'lucide-react';
import GalaxyBackground2D from './GalaxyBackground2D.jsx';

// Inline Python logo SVG data URI
const PYTHON_SVG = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><path fill="%23387eb8" d="M63.5 1.5c-30.8 0-28.8 13.3-28.8 13.3l.03 13.8h29.3v4.2H24.3C10.7 32.8 1.5 41.5 1.5 59.8c0 18.4 8 26.2 19.3 26.2h11.5v-16.1c0-12.2 10.5-22.9 22.9-22.9h29.2v-16.2c0-12.8-11.2-29.3-20.9-29.3zm-16.4 8.7c2.6 0 4.7 2.1 4.7 4.7s-2.1 4.7-4.7 4.7-4.7-2.1-4.7-4.7 2.1-4.7 4.7-4.7z"/><path fill="%23ffe052" d="M64.5 126.5c30.8 0 28.8-13.3 28.8-13.3l-.03-13.8H64v-4.2h39.7c13.6 0 22.8-8.7 22.8-27s-8-26.2-19.3-26.2H115.7v16.1c0 12.2-10.5 22.9-22.9 22.9H63.6v16.2c0 12.8 11.2 29.3 20.9 29.3zm16.4-8.7c-2.6 0-4.7-2.1-4.7-4.7s2.1-4.7 4.7-4.7 4.7 2.1 4.7 4.7-2.1 4.7-4.7 4.7z"/></svg>`;

// Preset cluster layout center points matching the reference image layout
const PRESET_CLUSTER_POSITIONS = {
  src: { x: -310, y: -160 },
  services: { x: 260, y: -170 },
  SolarFluxEngine: { x: -40, y: 190 },
  models: { x: -420, y: 190 },
  api: { x: 380, y: 40 },
  utils: { x: 330, y: 260 },
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
  const [nodeTypeFilter, setNodeTypeFilter] = useState('all'); // 'all' | 'file' | 'symbol'
  const [languageFilter, setLanguageFilter] = useState('python'); // 'all' | 'python' | 'javascript'
  const [dependencyFilter, setDependencyFilter] = useState('all'); // 'all' | 'imports' | 'calls' | 'defines' | 'contains' | 'cross'
  const [activeLayout, setActiveLayout] = useState('force'); // 'force' | 'hierarchical'

  // Available languages extracted dynamically from graph
  const availableLanguages = useMemo(() => {
    if (!graphData?.nodes) return ['python'];
    const langs = new Set(graphData.nodes.map((n) => n.language).filter(Boolean));
    return ['all', ...Array.from(langs)];
  }, [graphData]);

  // Compute Cytoscape elements (File child nodes + File-to-File edges only)
  // Containers are rendered via pure dynamic CSS overlay to match the reference design 100%
  const elements = useMemo(() => {
    if (!graphData || !Array.isArray(graphData.nodes)) return [];

    const elems = [];
    const activeNodeIds = new Set();

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

      // Node type filter
      if (nodeTypeFilter !== 'all') {
        if (nodeTypeFilter === 'file' && node.type !== 'file') return false;
        if (nodeTypeFilter === 'symbol' && node.type === 'file') return false;
      }

      // Language filter
      if (languageFilter !== 'all' && node.language && node.language.toLowerCase() !== languageFilter.toLowerCase()) {
        return false;
      }

      return true;
    });

    validNodes.forEach((n) => activeNodeIds.add(n.id));

    // 2. Add File Nodes
    validNodes.forEach((node) => {
      elems.push({
        group: 'nodes',
        data: {
          id: node.id,
          label: node.label,
          path: node.path,
          cluster: node.cluster,
          type: node.type,
          language: node.language,
          loc: node.metrics?.loc || 0,
          centrality: node.metrics?.centrality || 0,
          complexity: node.metrics?.complexity || 0,
          ai_summary: node.ai_summary,
        },
      });
    });

    // 3. Add Direct File-to-File Edges
    if (Array.isArray(graphData.edges)) {
      graphData.edges.forEach((edge) => {
        // File-to-file arrows only
        if (!activeNodeIds.has(edge.source) || !activeNodeIds.has(edge.target)) return;

        // Dependency relation filter
        if (dependencyFilter !== 'all') {
          if (dependencyFilter === 'cross' && !edge.is_cross_cluster) return;
          if (dependencyFilter !== 'cross' && edge.relation !== dependencyFilter) return;
        }

        elems.push({
          group: 'edges',
          data: {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            relation: edge.relation,
            weight: edge.weight,
            is_cross_cluster: edge.is_cross_cluster,
          },
        });
      });
    }

    return elems;
  }, [graphData, searchQuery, nodeTypeFilter, languageFilter, dependencyFilter]);

  // Update visual cluster container boxes based on rendered node bounding boxes
  const updateClusterBoxes = useCallback(() => {
    const cy = cyRef.current;
    if (!cy || !graphData?.clusters) return;

    const boxes = [];
    graphData.clusters.forEach((cluster) => {
      const nodesInCluster = cy.nodes(`[cluster = "${cluster.path}"]`);
      if (nodesInCluster.length === 0) return;

      const rbb = nodesInCluster.renderedBoundingBox();
      if (!rbb || rbb.w <= 0 || rbb.h <= 0) return;

      const padX = 28;
      const padTop = 50;
      const padBottom = 26;

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

  // Apply Cytoscape Layout
  const applyLayout = useCallback((layoutType = activeLayout) => {
    const cy = cyRef.current;
    if (!cy) return;

    if (layoutType === 'force') {
      // Position nodes inside their clusters cleanly
      const clusters = graphData?.clusters || [];
      clusters.forEach((cluster, cIdx) => {
        const basePos = PRESET_CLUSTER_POSITIONS[cluster.path] || {
          x: (cIdx % 3) * 360 - 360,
          y: Math.floor(cIdx / 3) * 320 - 160,
        };

        const childNodes = cy.nodes(`[cluster = "${cluster.path}"]`);
        const count = childNodes.length;

        // Clean relative positioning based on cluster size matching reference image
        childNodes.forEach((child, idx) => {
          let offsetX = 0;
          let offsetY = 0;

          if (cluster.path === 'src') {
            // 5 files: main.py top, routes.py left, telemetry.py right, models.py bottom-left, weather.py bottom-right
            const srcOffsets = [
              { x: -30, y: -65 },  // main.py
              { x: -95, y: -10 },  // routes.py
              { x: 55, y: -10 },   // telemetry.py
              { x: -75, y: 55 },   // models.py
              { x: 45, y: 55 },    // weather.py
            ];
            offsetX = srcOffsets[idx]?.x ?? (idx * 30);
            offsetY = srcOffsets[idx]?.y ?? (idx * 20);
          } else if (cluster.path === 'services') {
            // 3 files: data_fetcher.py top-right, processing.py left, api_client.py bottom-right
            const servOffsets = [
              { x: 60, y: -50 },   // data_fetcher.py
              { x: -70, y: 0 },    // processing.py
              { x: 70, y: 30 },    // api_client.py
            ];
            offsetX = servOffsets[idx]?.x ?? (idx * 40);
            offsetY = servOffsets[idx]?.y ?? (idx * 20);
          } else if (cluster.path === 'SolarFluxEngine') {
            // 4 files: engine.py top, magnetosphere.py left, solar.py right, prediction.py bottom
            const solarOffsets = [
              { x: -5, y: -60 },   // engine.py
              { x: -85, y: 0 },    // magnetosphere.py
              { x: 75, y: 0 },     // solar.py
              { x: -5, y: 55 },    // prediction.py
            ];
            offsetX = solarOffsets[idx]?.x ?? (idx * 30);
            offsetY = solarOffsets[idx]?.y ?? (idx * 20);
          } else if (cluster.path === 'models') {
            // 3 files: base.py top, forecast.py bottom-left, solar.py bottom-right
            const modOffsets = [
              { x: 0, y: -45 },    // base.py
              { x: -65, y: 15 },   // forecast.py
              { x: 50, y: 35 },    // solar.py
            ];
            offsetX = modOffsets[idx]?.x ?? (idx * 30);
            offsetY = modOffsets[idx]?.y ?? (idx * 20);
          } else if (cluster.path === 'api') {
            // 2 files: endpoints.py top, schemas.py bottom
            const apiOffsets = [
              { x: 0, y: -30 },    // endpoints.py
              { x: 5, y: 25 },     // schemas.py
            ];
            offsetX = apiOffsets[idx]?.x ?? 0;
            offsetY = apiOffsets[idx]?.y ?? 0;
          } else if (cluster.path === 'utils') {
            // 2 files: helpers.py top, constants.py bottom
            const utilOffsets = [
              { x: -5, y: -25 },   // helpers.py
              { x: 30, y: 25 },    // constants.py
            ];
            offsetX = utilOffsets[idx]?.x ?? 0;
            offsetY = utilOffsets[idx]?.y ?? 0;
          } else {
            // Generic dynamic grid for any backend repo
            const col = idx % 2;
            const row = Math.floor(idx / 2);
            offsetX = col === 0 ? -65 : 65;
            offsetY = row * 50 - 25;
          }

          child.position({
            x: basePos.x + offsetX,
            y: basePos.y + offsetY,
          });
        });
      });

      // Fit to screen smoothly
      cy.fit(undefined, 70);
      updateClusterBoxes();
    } else if (layoutType === 'hierarchical') {
      // ─── UNCLUSTERED ACCORDION / HIERARCHICAL PIPELINE LAYOUT ────────────────
      // Groups clusters into clean architectural tiers from top to bottom
      // Spreads clusters with ample room (vertical gap 380px, horizontal gap 420px)
      // Allows user to scroll and pan easily without any visual clutter or overlaps
      const clusters = graphData?.clusters || [];
      const edges = graphData?.edges || [];

      // Derive inter-cluster dependencies to compute topological level
      const clusterInDegree = {};
      const clusterOut = {};
      clusters.forEach((c) => {
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

      // Compute topological tier level for each cluster (0 = root / entrypoint, 1 = domain core, 2 = services, etc.)
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

      // Default any disconnected/cycle clusters
      clusters.forEach((c) => {
        if (clusterLevels[c.path] === undefined) {
          clusterLevels[c.path] = 1;
        }
      });

      // Group clusters by tier
      const tiers = {};
      clusters.forEach((c) => {
        const lvl = clusterLevels[c.path] || 0;
        if (!tiers[lvl]) tiers[lvl] = [];
        tiers[lvl].push(c);
      });

      // Position each tier with spacious, unclustered vertical and horizontal separation
      const TIER_HEIGHT = 380;
      const CLUSTER_WIDTH = 420;
      const tierKeys = Object.keys(tiers).map(Number).sort((a, b) => a - b);

      tierKeys.forEach((lvl) => {
        const clustersInTier = tiers[lvl];
        const tierY = (lvl - (tierKeys.length - 1) / 2) * TIER_HEIGHT;
        const totalW = (clustersInTier.length - 1) * CLUSTER_WIDTH;

        clustersInTier.forEach((cluster, colIdx) => {
          const clusterX = colIdx * CLUSTER_WIDTH - totalW / 2;
          const childNodes = cy.nodes(`[cluster = "${cluster.path}"]`);

          // Position files inside cluster box with generous breathing room
          childNodes.forEach((child, idx) => {
            const col = idx % 2;
            const row = Math.floor(idx / 2);
            const offsetX = col === 0 ? -70 : 70;
            const offsetY = row * 52 - 30;

            child.position({
              x: clusterX + offsetX,
              y: tierY + offsetY,
            });
          });
        });
      });

      // Zoom and center cleanly so user can scroll/pan naturally through tiers
      cy.animate({
        fit: { eles: cy.elements(), padding: 80 },
        duration: 400,
      });
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
      minZoom: 0.2,
      maxZoom: 3.5,
      style: [
        // ─── FILE NODES (Pills matching reference image) ─────────────────────
        {
          selector: 'node',
          style: {
            'shape': 'round-rectangle',
            'width': 134,
            'height': 34,
            'corner-radius': 10,
            'background-color': '#080e1e',
            'background-opacity': 0.95,
            'border-width': 1.6,
            'border-color': '#38bdf8', // glowing cyan default
            'border-opacity': 0.85,
            'label': 'data(label)',
            'color': '#f8fafc',
            'text-valign': 'center',
            'text-halign': 'center',
            'font-family': "'JetBrains Mono', 'Plus Jakarta Sans', monospace",
            'font-size': '11.5px',
            'font-weight': 600,
            'background-image': PYTHON_SVG,
            'background-fit': 'contain',
            'background-width': '16px',
            'background-height': '16px',
            'background-position-x': '12px',
            'background-position-y': '50%',
            'text-margin-x': '10px',
            'text-outline-color': '#080e1e',
            'text-outline-width': 1.5,
            'cursor': 'pointer',
            'transition-property': 'border-color, border-width, opacity, underlay-opacity',
            'transition-duration': '0.2s',
            'z-index': 10,
          },
        },
        // ─── FILE-TO-FILE DIRECTED EDGES ─────────────────────────────────────
        {
          selector: 'edge',
          style: {
            'width': 1.7,
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 1.15,
            'line-opacity': 0.65,
            'target-arrow-fill': 'filled',
            'transition-property': 'line-color, width, line-opacity, z-index',
            'transition-duration': '0.2s',
            'z-index': 5,
          },
        },
        // Edge color variations based on exact relation matching reference legend
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
            'line-color': '#38bdf8', // Blue/Cyan
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
            'line-color': '#10b981', // Green
            'target-arrow-color': '#10b981',
          },
        },

        // ─── SELECTION & FOCUS HIGHLIGHTING ──────────────────────────────────
        {
          selector: 'node.selected',
          style: {
            'border-color': '#f43f5e', // Neon pink/magenta border
            'border-width': 2.8,
            'border-opacity': 1.0,
            'background-color': '#1c102a',
            'underlay-color': '#f43f5e',
            'underlay-padding': 7,
            'underlay-opacity': 0.45,
            'underlay-shape': 'round-rectangle',
            'z-index': 99,
          },
        },
        {
          selector: 'node.connected-neighbor',
          style: {
            'border-width': 2.2,
            'border-opacity': 1.0,
            'opacity': 1.0,
            'z-index': 80,
          },
        },
        {
          selector: 'edge.highlighted-edge',
          style: {
            'width': 2.9,
            'line-opacity': 1.0,
            'target-arrow-fill': 'filled',
            'arrow-scale': 1.35,
            'z-index': 90,
          },
        },
        {
          selector: '.dimmed',
          style: {
            'opacity': 0.2,
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

    // Reset previous classes
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
          zoom: 1.25,
          duration: 400,
        });
        return;
      }
    }
    cy.fit(undefined, 70);
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
          background: 'rgba(7, 11, 22, 0.90)',
          backdropFilter: 'blur(16px)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1, minWidth: '320px' }}>
          {/* Search Input */}
          <div style={{ position: 'relative', flex: 1, maxWidth: '420px' }}>
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

          {/* Node Type Filter */}
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
            value={nodeTypeFilter}
            onChange={(e) => setNodeTypeFilter(e.target.value)}
          >
            <option value="all">All nodes</option>
            <option value="file">Files only</option>
            <option value="symbol">Symbols / Functions</option>
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
                {lang === 'all' ? 'All languages' : lang}
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
            <option value="imports">Imports only</option>
            <option value="calls">Function calls</option>
            <option value="defines">Defines</option>
            <option value="contains">Contains / Uses</option>
            <option value="cross">Cross-folder only</option>
          </select>
        </div>

        {/* Layout Toggle Buttons */}
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
            <span>Force Directed</span>
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
              setNodeTypeFilter('all');
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
                border: `1.6px solid ${box.color}`,
                borderRadius: '16px',
                boxShadow: `0 0 20px ${box.color}22, inset 0 0 15px ${box.color}0c`,
                pointerEvents: 'auto',
                cursor: 'pointer',
                transition: 'border-color 0.2s, background-color 0.2s',
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
              {/* Cluster Header matching reference image: folder icon + name on left, file count badge on right */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 14px',
                  userSelect: 'none',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
                  <Folder size={14} style={{ color: box.color }} />
                  <span
                    style={{
                      fontFamily: "'JetBrains Mono', 'Plus Jakarta Sans', monospace",
                      fontSize: '12px',
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
                    fontSize: '10.5px',
                    fontFamily: "'JetBrains Mono', monospace",
                    padding: '2px 8px',
                    borderRadius: '9999px',
                    backgroundColor: 'rgba(0, 0, 0, 0.45)',
                    border: `1px solid ${box.color}66`,
                    color: '#e2e8f0',
                  }}
                >
                  {box.count} files
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
            onClick={() => cyRef.current?.fit(undefined, 70)}
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
            {activeLayout === 'force' ? 'Force Directed' : 'Hierarchical'}
          </span>
        </div>

        {/* ─── BOTTOM GRAPH LEGEND MATCHING REFERENCE SNAPSHOT ─────────────── */}
        <div
          style={{
            position: 'absolute',
            bottom: '24px',
            right: '24px',
            zIndex: 25,
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            padding: '8px 16px',
            borderRadius: '12px',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            background: 'rgba(10, 16, 30, 0.88)',
            backdropFilter: 'blur(12px)',
            fontSize: '11px',
            fontFamily: 'var(--font-mono, monospace)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '12px', height: '12px', borderRadius: '3px', backgroundColor: 'rgba(244, 63, 94, 0.2)', border: '1px solid #f43f5e', display: 'inline-block' }} />
            <span style={{ color: '#d1d5db' }}>Folder (Cluster)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '16px', height: '8px', borderRadius: '3px', backgroundColor: '#080e1e', border: '1px solid #38bdf8', display: 'inline-block' }} />
            <span style={{ color: '#d1d5db' }}>File Node</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '16px', height: '8px', borderRadius: '3px', backgroundColor: '#1c102a', border: '1px solid #f43f5e', boxShadow: '0 0 6px #f43f5e', display: 'inline-block' }} />
            <span style={{ color: '#fda4af' }}>Selected Node</span>
          </div>
          <div style={{ width: '1px', height: '14px', backgroundColor: 'rgba(255, 255, 255, 0.15)' }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '14px', height: '2px', backgroundColor: '#f97316', display: 'inline-block' }} />
            <span style={{ color: '#f97316' }}>Dependency (imports)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '14px', height: '2px', backgroundColor: '#38bdf8', display: 'inline-block' }} />
            <span style={{ color: '#38bdf8' }}>Function Call</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '14px', height: '2px', backgroundColor: '#a855f7', display: 'inline-block' }} />
            <span style={{ color: '#a855f7' }}>Defines</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '14px', height: '2px', backgroundColor: '#10b981', display: 'inline-block' }} />
            <span style={{ color: '#10b981' }}>Contains / Uses</span>
          </div>
        </div>
      </div>
    </div>
  );
}
