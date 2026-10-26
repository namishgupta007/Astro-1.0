import { useState, useMemo, useEffect } from 'react';
import {
  FileCode,
  Folder,
  Sparkles,
  Copy,
  Check,
  MoreHorizontal,
  ChevronRight,
  Code2,
  GitFork,
  Layers,
  ArrowDownLeft,
  ArrowUpRight,
  Bot
} from 'lucide-react';

// SVG Python icon
function PythonIcon({ style = { width: 14, height: 14 } }) {
  return (
    <svg style={style} viewBox="0 0 128 128" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M63.5 1.5c-30.8 0-28.8 13.3-28.8 13.3l.03 13.8h29.3v4.2H24.3C10.7 32.8 1.5 41.5 1.5 59.8c0 18.4 8 26.2 19.3 26.2h11.5v-16.1c0-12.2 10.5-22.9 22.9-22.9h29.2v-16.2c0-12.8-11.2-29.3-20.9-29.3zm-16.4 8.7c2.6 0 4.7 2.1 4.7 4.7s-2.1 4.7-4.7 4.7-4.7-2.1-4.7-4.7 2.1-4.7 4.7-4.7z"
        fill="#387eb8"
      />
      <path
        d="M64.5 126.5c30.8 0 28.8-13.3 28.8-13.3l-.03-13.8H64v-4.2h39.7c13.6 0 22.8-8.7 22.8-27s-8-26.2-19.3-26.2H115.7v16.1c0 12.2-10.5 22.9-22.9 22.9H63.6v16.2c0 12.8 11.2 29.3 20.9 29.3zm16.4-8.7c-2.6 0-4.7-2.1-4.7-4.7s2.1-4.7 4.7-4.7 4.7 2.1 4.7 4.7-2.1 4.7-4.7 4.7z"
        fill="#ffe052"
      />
    </svg>
  );
}

export default function NodeInspectorPanel({
  selectedNode,
  selectedCluster,
  allNodes = [],
  allEdges = [],
  repoName = 'cosmic-weather-api',
  onSelectNode,
  onClose,
}) {
  const [activeTab, setActiveTab] = useState('overview'); // 'overview' | 'dependencies'
  const [copied, setCopied] = useState(false);

  // Compute incoming and outgoing dependencies for selected file
  const { incomingDeps, outgoingDeps } = useMemo(() => {
    if (!selectedNode || !Array.isArray(allEdges)) {
      return { incomingDeps: [], outgoingDeps: [] };
    }

    const nodeLookup = new Map();
    allNodes.forEach((n) => {
      nodeLookup.set(n.id, n);
      nodeLookup.set(n.path, n);
    });

    const incoming = allEdges
      .filter((e) => e.target === selectedNode.id || e.targetPath === selectedNode.path)
      .map((e) => {
        const sourceNode = nodeLookup.get(e.source) || nodeLookup.get(e.sourcePath);
        return {
          edgeId: e.id,
          nodeId: sourceNode?.id || e.source,
          label: sourceNode?.label || e.sourcePath?.split('/').pop() || e.source,
          path: sourceNode?.path || e.sourcePath || '',
          relation: e.relation,
        };
      });

    const outgoing = allEdges
      .filter((e) => e.source === selectedNode.id || e.sourcePath === selectedNode.path)
      .map((e) => {
        const targetNode = nodeLookup.get(e.target) || nodeLookup.get(e.targetPath);
        return {
          edgeId: e.id,
          nodeId: targetNode?.id || e.target,
          label: targetNode?.label || e.targetPath?.split('/').pop() || e.target,
          path: targetNode?.path || e.targetPath || '',
          relation: e.relation,
        };
      });

    return { incomingDeps: incoming, outgoingDeps: outgoing };
  }, [selectedNode, allNodes, allEdges]);


  const handleCopyPath = () => {
    if (!selectedNode?.path) return;
    navigator.clipboard.writeText(selectedNode.path);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // If a cluster/folder is selected
  if (!selectedNode && selectedCluster) {
    const clusterFiles = allNodes.filter((n) => n.cluster === selectedCluster.path);
    const totalLoc = clusterFiles.reduce((acc, f) => acc + (f.metrics?.loc || 0), 0);

    return (
      <aside className="workspace-drawer">
        <div className="inspector-badge-row">
          <span className="kicker-glow">DIRECTORY CLUSTER</span>
          <button
            type="button"
            style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer' }}
            onClick={onClose}
          >
            <MoreHorizontal size={16} />
          </button>
        </div>

        <div className="inspector-title-wrap">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <Folder size={20} style={{ color: selectedCluster.color || '#f43f5e' }} />
            <h3 className="inspector-node-title">{selectedCluster.name || selectedCluster.path}</h3>
          </div>
          <div className="inspector-path-pill">
            <span className="inspector-path-text">{selectedCluster.path}</span>
          </div>
        </div>

        <div className="inspector-metrics-section">
          <span className="kicker-glow">CONTAINED TELEMETRY</span>
          <div className="inspector-metrics-grid">
            <div className="inspector-metric-card">
              <span className="inspector-metric-label">Contained Files</span>
              <span className="inspector-metric-value">{clusterFiles.length}</span>
            </div>
            <div className="inspector-metric-card inspector-metric-card--highlight">
              <span className="inspector-metric-label">Total LOC</span>
              <span className="inspector-metric-value inspector-metric-value--orange">{totalLoc}</span>
            </div>
          </div>
        </div>

        <div>
          <span className="kicker-glow" style={{ display: 'block', marginBottom: '0.5rem' }}>
            FILES IN THIS CLUSTER ({clusterFiles.length})
          </span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
            {clusterFiles.map((file) => (
              <div
                key={file.id}
                className="inspector-dep-item"
                onClick={() => onSelectNode(file.id)}
              >
                <div className="inspector-dep-left">
                  <PythonIcon />
                  <span className="inspector-dep-name">{file.label}</span>
                </div>
                <ChevronRight size={13} style={{ color: '#64748b' }} />
              </div>
            ))}
          </div>
        </div>
      </aside>
    );
  }

  if (!selectedNode) {
    return (
      <aside className="workspace-drawer" style={{ alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
        <FileCode size={32} style={{ color: '#475569', marginBottom: '0.75rem' }} />
        <p style={{ fontSize: '0.8rem', fontFamily: 'var(--font-mono)', color: '#64748b', margin: 0 }}>
          Select a file or folder container in the dependency graph to inspect telemetry.
        </p>
      </aside>
    );
  }

  return (
    <aside className="workspace-drawer">
      {/* ─── HEADER ──────────────────────────────────────────────────────── */}
      <div className="inspector-badge-row">
        <span className="kicker-glow">NODE INSPECTOR</span>
        <button
          type="button"
          style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer' }}
          title="More options"
        >
          <MoreHorizontal size={16} />
        </button>
      </div>

      {/* ─── NODE HERO CARD ──────────────────────────────────────────────── */}
      <div className="inspector-title-wrap">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <div style={{
            width: '32px',
            height: '32px',
            borderRadius: '50%',
            background: 'rgba(6, 182, 212, 0.15)',
            border: '1px solid rgba(6, 182, 212, 0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <PythonIcon style={{ width: 18, height: 18 }} />
          </div>
          <h3 className="inspector-node-title">{selectedNode.label}</h3>
        </div>

        <div className="inspector-path-pill" style={{ justifyContent: 'space-between' }}>
          <span className="inspector-path-text">{selectedNode.path}</span>
          <button
            type="button"
            style={{ background: 'none', border: 'none', color: copied ? '#4ade80' : '#64748b', cursor: 'pointer', padding: 0 }}
            title="Copy path"
            onClick={handleCopyPath}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
          </button>
        </div>
      </div>

      {/* ─── TABS: OVERVIEW | DEPENDENCIES ───────────────────────────────── */}
      <div className="inspector-tab-row">
        <button
          type="button"
          className={`inspector-tab-btn ${activeTab === 'overview' ? 'inspector-tab-btn--active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          type="button"
          className={`inspector-tab-btn ${activeTab === 'dependencies' ? 'inspector-tab-btn--active' : ''}`}
          onClick={() => setActiveTab('dependencies')}
        >
          Dependencies
        </button>
      </div>

      {/* ─── TAB 1: OVERVIEW ─────────────────────────────────────────────── */}
      {activeTab === 'overview' && (
        <>
          {/* AI ARCHITECTURAL BRIEF */}
          <div className="inspector-summary-box">
            <div className="inspector-summary-tag">
              <Bot size={13} />
              <span>AI ARCHITECTURAL BRIEF</span>
            </div>
            <p className="inspector-summary-text">
              {selectedNode.ai_summary ||
                'Handles core logic, processing and dependency execution. Acts as a key architectural bridge across modules.'}
            </p>
          </div>

          {/* INCOMING DEPENDENCIES (3) */}
          <div className="inspector-deps-section">
            <div className="inspector-deps-header">
              <span className="inspector-deps-title">
                INCOMING DEPENDENCIES ({incomingDeps.length})
              </span>
              <span className="inspector-deps-viewall" onClick={() => setActiveTab('dependencies')}>
                View all →
              </span>
            </div>
            {incomingDeps.length === 0 ? (
              <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: '#64748b', fontStyle: 'italic' }}>
                No incoming dependencies
              </span>
            ) : (
              incomingDeps.map((dep, idx) => (
                <div
                  key={idx}
                  className="inspector-dep-item"
                  onClick={() => onSelectNode(dep.nodeId)}
                  title={`Select ${dep.path}`}
                >
                  <div className="inspector-dep-left">
                    <PythonIcon />
                    <span className="inspector-dep-name">{dep.label}</span>
                    <span className="inspector-dep-path">({dep.path})</span>
                  </div>
                  <ArrowDownLeft size={13} style={{ color: '#06b6d4' }} />
                </div>
              ))
            )}
          </div>

          {/* OUTGOING DEPENDENCIES (4) */}
          <div className="inspector-deps-section">
            <div className="inspector-deps-header">
              <span className="inspector-deps-title">
                OUTGOING DEPENDENCIES ({outgoingDeps.length})
              </span>
              <span className="inspector-deps-viewall" onClick={() => setActiveTab('dependencies')}>
                View all →
              </span>
            </div>
            {outgoingDeps.length === 0 ? (
              <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: '#64748b', fontStyle: 'italic' }}>
                No outgoing dependencies
              </span>
            ) : (
              outgoingDeps.map((dep, idx) => (
                <div
                  key={idx}
                  className="inspector-dep-item"
                  onClick={() => onSelectNode(dep.nodeId)}
                  title={`Select ${dep.path}`}
                >
                  <div className="inspector-dep-left">
                    <PythonIcon />
                    <span className="inspector-dep-name">{dep.label}</span>
                    <span className="inspector-dep-path">({dep.path})</span>
                  </div>
                  <ArrowUpRight size={13} style={{ color: '#fb923c' }} />
                </div>
              ))
            )}
          </div>

          {/* FILE METRICS */}
          <div className="inspector-metrics-section">
            <span className="kicker-glow">FILE METRICS</span>
            <div className="inspector-metrics-grid">
              <div className="inspector-metric-card">
                <span className="inspector-metric-label">LOC</span>
                <span className="inspector-metric-value">{selectedNode.metrics?.loc || 0}</span>
              </div>
              <div className="inspector-metric-card inspector-metric-card--highlight">
                <span className="inspector-metric-label">CENTRALITY</span>
                <span className="inspector-metric-value inspector-metric-value--orange">
                  {selectedNode.metrics?.centrality != null
                    ? Number(selectedNode.metrics.centrality).toFixed(2)
                    : '0.00'}
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="inspector-metric-label">COMPLEXITY</span>
                <span className="inspector-metric-value inspector-metric-value--peach">
                  {selectedNode.metrics?.complexity || 0}
                </span>
              </div>
              <div className="inspector-metric-card">
                <span className="inspector-metric-label">CLUSTER ID</span>
                <span className="inspector-metric-value">
                  #{selectedNode.position_hint?.cluster_id ?? selectedNode.metrics?.cluster_id ?? 0}
                </span>
              </div>
            </div>
          </div>
        </>
      )}

      {/* ─── TAB 2: DEPENDENCIES ─────────────────────────────────────────── */}
      {activeTab === 'dependencies' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
          <div>
            <span className="kicker-glow" style={{ display: 'block', marginBottom: '0.4rem' }}>
              INCOMING INVOCATIONS ({incomingDeps.length})
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              {incomingDeps.map((dep, i) => (
                <div
                  key={i}
                  className="inspector-dep-item"
                  onClick={() => onSelectNode(dep.nodeId)}
                >
                  <span className="inspector-dep-name">{dep.path}</span>
                  <span style={{
                    fontSize: '0.65rem',
                    fontFamily: 'var(--font-mono)',
                    padding: '0.15rem 0.4rem',
                    borderRadius: '4px',
                    background: 'rgba(6, 182, 212, 0.15)',
                    color: '#67e8f9',
                    border: '1px solid rgba(6, 182, 212, 0.3)'
                  }}>
                    {dep.relation}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div>
            <span className="kicker-glow" style={{ display: 'block', marginBottom: '0.4rem' }}>
              OUTGOING DEPENDENCIES ({outgoingDeps.length})
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              {outgoingDeps.map((dep, i) => (
                <div
                  key={i}
                  className="inspector-dep-item"
                  onClick={() => onSelectNode(dep.nodeId)}
                >
                  <span className="inspector-dep-name">{dep.path}</span>
                  <span style={{
                    fontSize: '0.65rem',
                    fontFamily: 'var(--font-mono)',
                    padding: '0.15rem 0.4rem',
                    borderRadius: '4px',
                    background: 'rgba(251, 146, 60, 0.15)',
                    color: '#fb923c',
                    border: '1px solid rgba(251, 146, 60, 0.3)'
                  }}>
                    {dep.relation}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
