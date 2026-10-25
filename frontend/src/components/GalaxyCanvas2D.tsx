/**
 * Astral Cartographer — 2D Knowledge Graph Canvas
 * Production-quality Cytoscape.js implementation with compound directory containers,
 * direct file-to-file dependency edges, and deep celestial styling.
 */

import React, { useMemo } from 'react';
import CytoscapeGalaxyGraph from './Graph2D/CytoscapeGalaxyGraph.jsx';
import { normalizeGraphData } from '../services/graphNormalizer.js';
import { GraphEdge, GraphNode, Workflow } from '../types/galaxy';

interface GalaxyCanvas2DProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeId: string | null;
  activeWorkflow?: Workflow | null;
  activeTypeFilter?: string;
  onSelectNode: (node: GraphNode | null) => void;
}

export const GalaxyCanvas2D: React.FC<GalaxyCanvas2DProps> = ({
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
}) => {
  const normalized = useMemo(() => {
    return normalizeGraphData({
      repo_name: 'cosmic-weather-api',
      nodes: nodes || [],
      edges: edges || [],
    });
  }, [nodes, edges]);

  return (
    <div className="w-full h-full relative">
      <CytoscapeGalaxyGraph
        graphData={normalized}
        selectedNodeId={selectedNodeId}
        onSelectNode={(id) => {
          if (!id) {
            onSelectNode(null);
            return;
          }
          const found = nodes.find((n) => n.id === id) || null;
          onSelectNode(found);
        }}
      />
    </div>
  );
};
