import { useEffect, useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  Share2,
  FolderTree,
  Search,
  Bot,
  Activity,
  Layers,
  FileCode,
  Box,
  Terminal,
  ExternalLink,
  Cpu,
  GitFork
} from 'lucide-react';
import GalaxyGraph3D from '../components/Graph/GalaxyGraph3D.jsx';
import CytoscapeGalaxyGraph from '../components/Graph2D/CytoscapeGalaxyGraph.jsx';
import NodeInspectorPanel from '../components/Graph2D/NodeInspectorPanel.jsx';
import { getRepositoryGraph, askCodebaseQuestion } from '../api/workspaceService.js';
import SiteFooter from '../components/SiteFooter.jsx';
import '../styles/workspace.css';

export default function Workspace() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const repoParam = searchParams.get('repo') || 'cosmic-weather-api';

  // Navigation tab states: 'graph2d' | 'graph' | 'explorer' | 'overview' | 'search' | 'ai' | 'status'
  const [activeTab, setActiveTab] = useState('graph2d');

  // Data & graph states
  const [graphData, setGraphData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedNodeId, setSelectedNodeId] = useState('file::src/telemetry.py');
  const [selectedCluster, setSelectedCluster] = useState(null);
  const [highlightedNodeIds, setHighlightedNodeIds] = useState([]);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');

  // AI Chat state
  const [chatMessages, setChatMessages] = useState([
    {
      sender: 'ai',
      text: "Greetings! I'm your Astral Cartographer AI agent. I can guide your camera through the codebase, explain architectural workflows, or trace blast radius impacts."
    }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [isAsking, setIsAsking] = useState(false);

  // Load graph payload
  useEffect(() => {
    async function load() {
      setLoading(true);
      const data = await getRepositoryGraph(repoParam);
      setGraphData(data);
      if (data?.nodes?.length > 0) {
        const telemetry = data.nodes.find((n) => n.id.includes('telemetry.py') || n.label === 'telemetry.py');
        setSelectedNodeId(telemetry ? telemetry.id : data.nodes[0].id);
      }
      setLoading(false);
    }
    load();
  }, [repoParam]);

  // Selected Node data
  const selectedNode = useMemo(() => {
    if (!graphData?.nodes || !selectedNodeId) return null;
    return graphData.nodes.find((n) => n.id === selectedNodeId) || null;
  }, [graphData, selectedNodeId]);

  // Filtered nodes for Search & Explorer
  const filteredNodes = useMemo(() => {
    if (!graphData?.nodes) return [];
    if (!searchQuery.trim()) return graphData.nodes;
    const q = searchQuery.toLowerCase();
    return graphData.nodes.filter(
      (n) =>
        n.label.toLowerCase().includes(q) ||
        n.path.toLowerCase().includes(q) ||
        n.type.toLowerCase().includes(q)
    );
  }, [graphData, searchQuery]);

  // Handle AI question submit
  const handleSendChat = async (e) => {
    e?.preventDefault();
    if (!chatInput.trim() || isAsking) return;

    const userQ = chatInput.trim();
    setChatInput('');
    setChatMessages((prev) => [...prev, { sender: 'user', text: userQ }]);
    setIsAsking(true);

    try {
      const resp = await askCodebaseQuestion(userQ, repoParam);
      setChatMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          text: resp.answer,
          highlights: resp.highlighted_node_ids
        }
      ]);
      if (resp.highlighted_node_ids?.length > 0) {
        setHighlightedNodeIds(resp.highlighted_node_ids);
        setSelectedNodeId(resp.highlighted_node_ids[0]);
      }
    } catch {
      setChatMessages((prev) => [
        ...prev,
        { sender: 'ai', text: "Encountered an issue analyzing the codebase query. Please try again." }
      ]);
    } finally {
      setIsAsking(false);
    }
  };

  return (
    <div className="workspace-layout">
      {/* Header */}
      <header className="workspace-header">
        <div className="workspace-header__left">
          <button
            type="button"
            className="workspace-back-btn"
            onClick={() => navigate('/dashboard')}
          >
            <ArrowLeft size={14} /> Home
          </button>
          <div className="workspace-repo-title">
            <span className="workspace-repo-name">
              {graphData?.repo_name || repoParam.split('/').pop()}
            </span>
            <span className="workspace-branch-badge">
              git:{graphData?.branch || 'main'}
            </span>
          </div>
        </div>

        <div className="workspace-header__right">
          <span className="workspace-status-pill workspace-status-pill--ready">
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: graphData?.is_demo !== false ? '#fb923c' : '#38bdf8',
                display: 'inline-block',
                marginRight: 6
              }}
            />
            {graphData?.is_demo !== false ? 'DEMO DATA • INDEXED' : 'INDEXED READY'}
          </span>
        </div>
      </header>

      {/* Tabs Bar */}
      <nav className="workspace-tabs">
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'graph2d' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('graph2d')}
        >
          <GitFork size={15} /> Code Graph (2D)
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'graph' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('graph')}
        >
          <Share2 size={15} /> Code Graph (3D)
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'explorer' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('explorer')}
        >
          <FolderTree size={15} /> File Explorer
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'overview' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <Layers size={15} /> Overview
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'search' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('search')}
        >
          <Search size={15} /> Code Search
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'ai' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('ai')}
        >
          <Bot size={15} /> AI Assistant
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'status' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('status')}
        >
          <Activity size={15} /> Indexing Status
        </button>
      </nav>

      {/* Main Viewport */}
      <div className="workspace-viewport">
        {/* Tab 1: 2D Code Graph (Cytoscape.js) */}
        {activeTab === 'graph2d' && (
          <div className="workspace-view workspace-view--graph">
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#38bdf8', fontFamily: 'var(--font-mono)' }}>
                INITIALIZING 2D DEPENDENCY TOPOLOGY...
              </div>
            ) : (
              <CytoscapeGalaxyGraph
                graphData={graphData}
                selectedNodeId={selectedNodeId}
                onSelectNode={(id) => {
                  setSelectedNodeId(id);
                  setSelectedCluster(null);
                }}
                onSelectCluster={(cluster) => {
                  setSelectedCluster(cluster);
                  setSelectedNodeId(null);
                }}
              />
            )}
          </div>
        )}

        {/* Tab 2: 3D Code Graph */}
        {activeTab === 'graph' && (
          <div className="workspace-view workspace-view--graph">
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#00e5ff', fontFamily: 'var(--font-mono)' }}>
                INITIALIZING CELESTIAL MAPPING...
              </div>
            ) : (
              <GalaxyGraph3D
                graphData={graphData}
                selectedNodeId={selectedNodeId}
                highlightedNodeIds={highlightedNodeIds}
                onSelectNode={(id) => {
                  setSelectedNodeId(id);
                  setSelectedCluster(null);
                }}
              />
            )}
          </div>
        )}

        {/* Tab 3: File Explorer */}
        {activeTab === 'explorer' && (
          <div className="workspace-view">
            <h2 className="text-lg font-semibold mb-4 text-cyan-300" style={{ color: '#67e8f9', marginBottom: '1rem' }}>
              Repository Structure
            </h2>
            <div className="explorer-tree">
              {filteredNodes.map((n) => (
                <div
                  key={n.id}
                  className={`explorer-item ${selectedNodeId === n.id ? 'explorer-item--active' : ''}`}
                  onClick={() => {
                    setSelectedNodeId(n.id);
                    setSelectedCluster(null);
                  }}
                >
                  {n.type === 'directory' ? <Box size={14} style={{ color: '#00e5ff' }} /> : <FileCode size={14} />}
                  <span>{n.path}</span>
                  <span style={{ fontSize: '0.75rem', color: '#64748b', marginLeft: 'auto' }}>{n.type}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 4: Overview */}
        {activeTab === 'overview' && (
          <div className="workspace-view" style={{ maxWidth: '900px', margin: '0 auto' }}>
            <div style={{ marginBottom: '2rem' }}>
              <p className="kicker-glow">ARCHITECTURAL TELEMETRY</p>
              <h2 className="overview-hero-title">
                Galaxy <em>Intelligence</em>
              </h2>
              <p className="overview-subtitle">
                Structural mapping, Louvain community clusters, and execution graph insights.
              </p>
            </div>

            <div className="overview-cards-grid">
              <div className="glow-feature-card glow-feature-card--orange">
                <div className="glow-icon-wrap glow-icon-wrap--orange">
                  <Box size={18} />
                </div>
                <div className="glow-card-metric">{graphData?.nodes?.length || 0}</div>
                <h3 className="glow-card-title">Total Nodes</h3>
                <p className="glow-card-desc">
                  Indexed structural entities including source files, modules, and callable functions.
                </p>
                <div className="glow-card-footer">
                  <span>Architecture Nodes</span>
                  <span>→</span>
                </div>
              </div>

              <div className="glow-feature-card glow-feature-card--peach">
                <div className="glow-icon-wrap glow-icon-wrap--peach">
                  <Share2 size={18} />
                </div>
                <div className="glow-card-metric">{graphData?.edges?.length || 0}</div>
                <h3 className="glow-card-title">Dependency Edges</h3>
                <p className="glow-card-desc">
                  Directed call graphs, module import chains, containment links, and subclass hierarchies.
                </p>
                <div className="glow-card-footer">
                  <span>Graph Traversal</span>
                  <span>→</span>
                </div>
              </div>

              <div className="glow-feature-card glow-feature-card--dark">
                <div className="glow-icon-wrap glow-icon-wrap--dark">
                  <Cpu size={18} />
                </div>
                <div className="glow-card-metric">{graphData?.clusters?.length || 6}</div>
                <h3 className="glow-card-title">Directory Clusters</h3>
                <p className="glow-card-desc">
                  Visual containment groups structuring child source files into module boundaries.
                </p>
                <div className="glow-card-footer">
                  <span>Module Domains</span>
                  <span>→</span>
                </div>
              </div>
            </div>

            {graphData?.workflows && graphData.workflows.length > 0 && (
              <div className="workflow-section" style={{ marginTop: '2.5rem' }}>
                <h3 className="workflow-section-title">
                  <Terminal size={16} /> Execution Workflows
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '1rem' }}>
                  {graphData.workflows.map((wf, idx) => (
                    <div key={idx} className="workflow-card">
                      <div className="workflow-card-head">
                        <span className="workflow-name">{wf.name}</span>
                        <span className="workflow-badge">{wf.nodes?.length || 0} stages</span>
                      </div>
                      <p className="workflow-desc">{wf.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 5: Search */}
        {activeTab === 'search' && (
          <div className="workspace-view" style={{ maxWidth: '800px', margin: '0 auto' }}>
            <div className="search-bar-wrap">
              <input
                type="text"
                className="search-input"
                placeholder="Search files, symbols, functions, classes..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                autoFocus
              />
            </div>
            <div className="explorer-tree">
              {filteredNodes.map((n) => (
                <div
                  key={n.id}
                  className={`explorer-item ${selectedNodeId === n.id ? 'explorer-item--active' : ''}`}
                  onClick={() => {
                    setSelectedNodeId(n.id);
                    setSelectedCluster(null);
                  }}
                >
                  <Search size={14} style={{ color: '#00e5ff' }} />
                  <span style={{ fontWeight: 600 }}>{n.label}</span>
                  <span style={{ fontSize: '0.75rem', color: '#64748b', fontFamily: 'var(--font-mono)' }}>({n.path})</span>
                  <span style={{ fontSize: '0.75rem', color: '#94a3b8', marginLeft: 'auto' }}>{n.type}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 6: AI Assistant */}
        {activeTab === 'ai' && (
          <div className="workspace-view">
            <div className="chat-container">
              <div className="chat-history">
                {chatMessages.map((msg, i) => (
                  <div
                    key={i}
                    className={`chat-message ${msg.sender === 'user' ? 'chat-message--user' : 'chat-message--ai'}`}
                  >
                    <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', fontFamily: 'var(--font-mono)', color: '#9ca3af', marginBottom: '0.25rem' }}>
                      {msg.sender === 'user' ? 'You' : 'Astral Agent'}
                    </div>
                    <div>{msg.text}</div>
                    {msg.highlights && (
                      <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: '#67e8f9' }}>
                        ⚡ Highlighted {msg.highlights.length} nodes in Galaxy
                      </div>
                    )}
                  </div>
                ))}
                {isAsking && (
                  <div className="chat-message chat-message--ai" style={{ fontSize: '0.85rem', fontFamily: 'var(--font-mono)', color: '#00e5ff' }}>
                    Traversing graph topology & synthesizing response...
                  </div>
                )}
              </div>
              <form onSubmit={handleSendChat} className="chat-input-row">
                <input
                  type="text"
                  className="chat-input-field"
                  placeholder="Ask anything about architecture, workflows, or impact radius..."
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                />
                <button type="submit" className="chat-send-btn" disabled={isAsking}>
                  Send
                </button>
              </form>
            </div>
          </div>
        )}

        {/* Tab 7: Indexing Status */}
        {activeTab === 'status' && (
          <div className="workspace-view" style={{ maxWidth: '700px', margin: '0 auto' }}>
            <div style={{ marginBottom: '1.5rem' }}>
              <p className="kicker-glow">INDEXING ENGINE</p>
              <h2 className="overview-hero-title">
                Telemetry <em>Pipeline</em>
              </h2>
            </div>

            <div className="status-pipeline-box">
              <div className="status-pipeline-header">
                <span style={{ fontWeight: 600, fontSize: '0.88rem', letterSpacing: '0.02em' }}>Pipeline Execution</span>
                <span className="status-pipeline-badge">100% COMPLETE</span>
              </div>
              <div className="status-progress-track">
                <div className="status-progress-bar" />
              </div>
              <div className="status-steps-list">
                <div className="status-step-item">
                  <span className="status-check-icon">✓</span>
                  <span>Repository cloned & AST parsed via Tree-sitter</span>
                </div>
                <div className="status-step-item">
                  <span className="status-check-icon">✓</span>
                  <span>NetworkX PageRank & Louvain community clusters computed</span>
                </div>
                <div className="status-step-item">
                  <span className="status-check-icon">✓</span>
                  <span>3D celestial galaxy coordinates & 2D dependency topology computed</span>
                </div>
                <div className="status-step-item">
                  <span className="status-check-icon">✓</span>
                  <span>LangGraph Q&A camera targeting initialized</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ─── SIDE INSPECTOR DRAWER ───────────────────────────────────────── */}
        {(selectedNode || selectedCluster) && (
          <NodeInspectorPanel
            selectedNode={selectedNode}
            selectedCluster={selectedCluster}
            allNodes={graphData?.nodes || []}
            allEdges={graphData?.edges || []}
            repoName={graphData?.repo_name || repoParam}
            onSelectNode={(id) => {
              setSelectedNodeId(id);
              setSelectedCluster(null);
            }}
            onClose={() => {
              setSelectedNodeId(null);
              setSelectedCluster(null);
            }}
          />
        )}
      </div>

      {/* Shared Global Site Footer */}
      <SiteFooter compact />
    </div>
  );
}

