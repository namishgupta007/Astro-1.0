import { useEffect, useState, useRef, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  Terminal,
  Cpu,
  Layers,
  Network,
  Share2,
  Sparkles,
  GitBranch,
  FolderGit2,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  Copy,
  Check,
  RefreshCw,
  Home
} from 'lucide-react';
import { submitRepositoryIndexing, getJobStreamUrl, getJobStatus, getRepositoryGraph } from '../api/workspaceService.js';
import useAuth from '../hooks/useAuth.js';
import { saveUserSingleRepository } from '../api/userRepoService.js';
import { RingedPlanetLogo } from './Landing.jsx';
import PipelineGalaxyCanvas from '../components/Graph/PipelineGalaxyCanvas.jsx';
import SiteFooter from '../components/SiteFooter.jsx';
import '../styles/analyze.css';

// 9 Canonical Astrograph Pipeline Stages
const PIPELINE_STAGES = [
  {
    id: 'ingestion',
    name: 'Repository Ingestion',
    subtext: 'Validating URL, permissions & metadata...',
    icon: FolderGit2,
  },
  {
    id: 'source_retrieval',
    name: 'Source Retrieval',
    subtext: 'Discovering files & filtering source tree...',
    icon: Layers,
  },
  {
    id: 'ast_parsing',
    name: 'Language Detection & AST Parsing',
    subtext: 'Parsing Tree-sitter abstract syntax trees...',
    icon: Cpu,
  },
  {
    id: 'dependency_extraction',
    name: 'Dependency Extraction',
    subtext: 'Resolving imports & directed call targets...',
    icon: Network,
  },
  {
    id: 'graph_construction',
    name: 'Knowledge Graph Construction',
    subtext: 'Building NetworkX topological code graph...',
    icon: Share2,
  },
  {
    id: 'architecture_analysis',
    name: 'Architecture & Centrality Analysis',
    subtext: 'Computing PageRank & Louvain clustering...',
    icon: Sparkles,
  },
  {
    id: 'ai_insights',
    name: 'AI Insights',
    subtext: 'Synthesizing contextual module summaries...',
    icon: Sparkles,
  },
  {
    id: 'galaxy_preparation',
    name: '3D Galaxy Preparation',
    subtext: 'Assigning celestial coordinates & clusters...',
    icon: Network,
  },
  {
    id: 'workspace_ready',
    name: 'Workspace Ready',
    subtext: 'Initializing interactive 3D galaxy canvas...',
    icon: CheckCircle2,
  },
];

export default function Analyze() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const repoUrl = searchParams.get('repo') || '';
  const repoIdParam = searchParams.get('repo_id') || '';
  const jobIdParam = searchParams.get('job_id') || '';
  const nameParam = searchParams.get('name') || '';
  const branchParam = searchParams.get('branch') || 'main';
  const [activeRepoId, setActiveRepoId] = useState(repoIdParam);

  // Parse repo owner and name from URL cleanly
  const repoMeta = useMemo(() => {
    const raw = repoUrl.replace(/^https?:\/\/(www\.)?github\.com\//i, '').replace(/\.git$/i, '').replace(/\/$/, '');
    const parts = raw.split('/');
    return {
      fullName: parts.length >= 2 ? `${parts[0]}/${parts[1]}` : (raw || 'my-repository'),
      owner: parts[0] || 'repository',
      name: parts[1] || parts[0] || 'project',
      branch: branchParam,
    };
  }, [repoUrl, branchParam]);

  // Pipeline execution states
  const [currentStageId, setCurrentStageId] = useState('ingestion');
  const [stageStatuses, setStageStatuses] = useState({
    ingestion: 'running',
    source_retrieval: 'pending',
    ast_parsing: 'pending',
    dependency_extraction: 'pending',
    graph_construction: 'pending',
    architecture_analysis: 'pending',
    ai_insights: 'pending',
    galaxy_preparation: 'pending',
    workspace_ready: 'pending',
  });

  const [progress, setProgress] = useState(8);
  const [statusMessage, setStatusMessage] = useState('Validating repository metadata and accessibility...');
  const [isCompleted, setIsCompleted] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  // Live Metrics
  const [metrics, setMetrics] = useState({
    filesDiscovered: null,
    filesParsed: null,
    symbolsExtracted: null,
    dependencyEdges: null,
    graphNodes: null,
    communitiesDetected: null,
    stageDuration: '0.0s',
  });

  // Telemetry Terminal
  const [logs, setLogs] = useState([]);
  const [isAutoScroll, setIsAutoScroll] = useState(true);
  const [isTerminalExpanded, setIsTerminalExpanded] = useState(false);
  const [copiedLogs, setCopiedLogs] = useState(false);
  const logBoxRef = useRef(null);

  // Live Elapsed Timer
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Auto transition countdown
  const [autoCountdown, setAutoCountdown] = useState(5);

  // Live seconds ticker
  useEffect(() => {
    if (isCompleted || errorMessage) return;
    const interval = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [isCompleted, errorMessage]);

  // Terminal Auto-scroll
  useEffect(() => {
    if (isAutoScroll && logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
    }
  }, [logs, isAutoScroll]);

  // Copy logs helper
  const handleCopyLogs = () => {
    const text = logs.map((l) => `[${l.timestamp}] [${l.level}] ${l.text}`).join('\n');
    navigator.clipboard.writeText(text);
    setCopiedLogs(true);
    setTimeout(() => setCopiedLogs(false), 2000);
  };

  // Safe append log helper (bounded to 200 items)
  const appendLog = (level, text) => {
    const timestamp = new Date().toTimeString().split(' ')[0];
    setLogs((prev) => {
      const next = [...prev, { timestamp, level, text }];
      return next.length > 200 ? next.slice(next.length - 200) : next;
    });
  };

  // Main Pipeline Runner (Connected to backend SSE + polling fallback)
  useEffect(() => {
    let isCancelled = false;
    let eventSource = null;
    let pollInterval = null;

    const isDemoMode = repoUrl === 'cosmic-weather-api' || repoUrl.includes('cosmic-weather-api');

    if (!repoUrl && !repoIdParam) {
      setErrorMessage('No repository provided. Please return to the dashboard and submit a repository or ZIP archive.');
      return;
    }

    appendLog('INGEST', `Initiating celestial analysis session for ${nameParam || repoMeta.fullName} [ref: ${branchParam}]`);

    // Backend stage mapping to 9 Canonical Frontend UI Stages
    const STAGE_MAP = {
      downloading: { id: 'ingestion', progress: 15, msg: 'Streaming repository archive from GitHub...' },
      extracting: { id: 'source_retrieval', progress: 30, msg: 'Safely extracting repository archive...' },
      scanning: { id: 'source_retrieval', progress: 45, msg: 'Scanning repository source files & directory tree...' },
      parsing_python: { id: 'ast_parsing', progress: 60, msg: 'Parsing Python syntax trees with Tree-sitter...' },
      parsing_javascript: { id: 'ast_parsing', progress: 75, msg: 'Parsing JavaScript & TypeScript ASTs...' },
      building_graph: { id: 'dependency_extraction', progress: 85, msg: 'Constructing unified topological dependency graph...' },
      analyzing_graph: { id: 'architecture_analysis', progress: 92, msg: 'Computing PageRank and community clustering...' },
      saving_results: { id: 'galaxy_preparation', progress: 98, msg: 'Finalizing graph artifacts and cache...' },
      completed: { id: 'workspace_ready', progress: 100, msg: 'Your code universe is ready.' },
    };

    function applyStageUpdate(backendStage, backendStatus, backendProgress, message) {
      const mapped = STAGE_MAP[backendStage] || { id: backendStage || 'ingestion', progress: backendProgress || 50, msg: message || 'Analyzing...' };
      setCurrentStageId(mapped.id);
      if (backendProgress !== undefined && backendProgress !== null) {
        setProgress(backendProgress);
      } else {
        setProgress(mapped.progress);
      }
      setStatusMessage(message || mapped.msg);
      appendLog('STAGE', `[Stage: ${backendStage || mapped.id}] ${message || mapped.msg} (${backendProgress ?? mapped.progress}%)`);

      setStageStatuses((prev) => {
        const next = { ...prev };
        let found = false;
        for (const s of PIPELINE_STAGES) {
          if (s.id === mapped.id) {
            next[s.id] = (backendStatus === 'completed' || backendStage === 'completed') ? 'completed' : 'running';
            found = true;
          } else if (!found) {
            next[s.id] = 'completed';
          }
        }
        return next;
      });
    }

    async function startPipeline() {
      if (isDemoMode) {
        runClientSimulation();
        return;
      }

      try {
        let jobId = jobIdParam;
        let repositoryId = repoIdParam;

        if (!jobId) {
          appendLog('INGEST', `Queueing indexing job with backend for ${repoUrl}...`);
          const submitRes = await submitRepositoryIndexing(repoUrl, repoMeta.branch, user?.uid, user?.email);
          jobId = submitRes?.job_id;
          repositoryId = submitRes?.repository_id;
        }

        if (repositoryId) {
          setActiveRepoId(repositoryId);
        }

        if (!jobId) {
          throw new Error('Backend did not return an indexing job ID');
        }

        appendLog('INFO', `Connected to backend indexing job: ${jobId}`);

        // Connect SSE stream
        const streamUrl = getJobStreamUrl(jobId);
        try {
          eventSource = new EventSource(streamUrl);

          eventSource.onmessage = (event) => {
            if (isCancelled) return;
            try {
              const data = JSON.parse(event.data);
              if (data.status === 'failed') {
                setErrorMessage(data.error_message || data.error || 'Pipeline indexing failed on server.');
                if (eventSource) eventSource.close();
                return;
              }

              applyStageUpdate(data.stage, data.status, data.progress, data.message);

              if (data.status === 'completed' || data.stage === 'completed' || (data.progress !== undefined && data.progress >= 100)) {
                if (eventSource) eventSource.close();
                finishPipeline(repositoryId);
              }
            } catch (err) {
              // ignore parse errors
            }
          };

          eventSource.onerror = () => {
            if (eventSource) {
              eventSource.close();
              eventSource = null;
            }
            // Fall back to HTTP polling if SSE drops
            if (!pollInterval && !isCancelled) {
              appendLog('INFO', 'SSE disconnected; continuing via polling...');
              pollInterval = setInterval(async () => {
                if (isCancelled) {
                  clearInterval(pollInterval);
                  return;
                }
                try {
                  const job = await getJobStatus(jobId);
                  applyStageUpdate(job.stage, job.status, job.progress, job.error_message);
                  if (job.status === 'completed') {
                    clearInterval(pollInterval);
                    finishPipeline(repositoryId);
                  } else if (job.status === 'failed') {
                    clearInterval(pollInterval);
                    setErrorMessage(job.error_message || 'Pipeline indexing failed on server.');
                  }
                } catch {
                  // ignore polling network errors
                }
              }, 1500);
            }
          };
        } catch {
          // If SSE creation fails, start polling immediately
          pollInterval = setInterval(async () => {
            if (isCancelled) {
              clearInterval(pollInterval);
              return;
            }
            try {
              const job = await getJobStatus(jobId);
              applyStageUpdate(job.stage, job.status, job.progress, job.error_message);
              if (job.status === 'completed') {
                clearInterval(pollInterval);
                finishPipeline(repositoryId);
              } else if (job.status === 'failed') {
                clearInterval(pollInterval);
                setErrorMessage(job.error_message || 'Pipeline indexing failed on server.');
              }
            } catch {
              // ignore
            }
          }, 1500);
        }
      } catch (err) {
        setErrorMessage(err.message || 'Failed to submit repository for indexing. Ensure backend is running.');
      }
    }

    // High-fidelity client pipeline execution matching real backend Cartographer steps
    function runClientSimulation() {
      const steps = [
        {
          stage: 'ingestion',
          progress: 14,
          message: `Validating repository access: ${repoMeta.fullName}...`,
          log: { level: 'INGEST', text: `Resolved remote git tree ref: ${repoMeta.fullName} [HTTP 200 OK]` },
          delay: 450,
          metricsUpdate: { stageDuration: '0.5s' }
        },
        {
          stage: 'source_retrieval',
          progress: 26,
          message: 'Retrieving repository source files and project structure...',
          log: { level: 'SCAN', text: 'Safe archive downloaded. Enumerating directory hierarchy and source files' },
          delay: 950,
          metricsUpdate: { filesDiscovered: 42, stageDuration: '1.0s' }
        },
        {
          stage: 'ast_parsing',
          progress: 44,
          message: 'Detecting languages & parsing Tree-sitter abstract syntax trees...',
          log: { level: 'AST', text: 'Detected Python & JavaScript/TypeScript. Parsed 38 files into Tree-sitter ASTs' },
          delay: 1550,
          metricsUpdate: { filesParsed: 38, symbolsExtracted: 184, stageDuration: '1.6s' }
        },
        {
          stage: 'dependency_extraction',
          progress: 58,
          message: 'Resolving imports, references & directed dependency edges...',
          log: { level: 'DEPENDENCY', text: 'Extracted 392 directed dependency links between modules, functions, and classes' },
          delay: 2150,
          metricsUpdate: { dependencyEdges: 392, stageDuration: '2.2s' }
        },
        {
          stage: 'graph_construction',
          progress: 72,
          message: 'Constructing NetworkX topological code graph...',
          log: { level: 'GRAPH', text: 'Assembled topological digraph with 184 structural and functional nodes' },
          delay: 2750,
          metricsUpdate: { graphNodes: 184, stageDuration: '2.8s' }
        },
        {
          stage: 'architecture_analysis',
          progress: 84,
          message: 'Computing PageRank centrality & Louvain community clustering...',
          log: { level: 'METRICS', text: 'Eigenvector centrality calculated. Louvain detected 4 distinct modular communities' },
          delay: 3350,
          metricsUpdate: { communitiesDetected: 4, stageDuration: '3.4s' }
        },
        {
          stage: 'ai_insights',
          progress: 89,
          message: 'Synthesizing contextual module summaries & architecture workflows...',
          log: { level: 'AI', text: 'Architectural context prepared. Mapped core workflows & blast radius schemas' },
          delay: 3900,
          metricsUpdate: { stageDuration: '3.9s' }
        },
        {
          stage: 'galaxy_preparation',
          progress: 96,
          message: 'Mapping symbols into celestial nodes and 3D galaxy coordinates...',
          log: { level: 'RENDER', text: 'Allocated spherical cluster shells. Serialized 3D celestial coordinates' },
          delay: 4450,
          metricsUpdate: { stageDuration: '4.5s' }
        },
        {
          stage: 'workspace_ready',
          progress: 100,
          message: 'Your code universe is ready.',
          log: { level: 'READY', text: 'Constellation initialized successfully. Your code universe is ready!' },
          delay: 4950,
          metricsUpdate: { stageDuration: '5.0s' }
        },
      ];

      steps.forEach((step) => {
        setTimeout(() => {
          if (isCancelled) return;
          setCurrentStageId(step.stage);
          setProgress(step.progress);
          setStatusMessage(step.message);

          if (step.log) {
            appendLog(step.log.level, step.log.text);
          }

          if (step.metricsUpdate) {
            setMetrics((prev) => ({ ...prev, ...step.metricsUpdate }));
          }

          setStageStatuses((prev) => {
            const next = { ...prev };
            let found = false;
            for (const s of PIPELINE_STAGES) {
              if (s.id === step.stage) {
                next[s.id] = step.stage === 'workspace_ready' ? 'completed' : 'running';
                found = true;
              } else if (!found) {
                next[s.id] = 'completed';
              }
            }
            return next;
          });

          if (step.stage === 'workspace_ready') {
            finishPipeline();
          }
        }, step.delay);
      });
    }

    async function finishPipeline(repoId) {
      const resolvedId = repoId || activeRepoId || repoIdParam;
      if (resolvedId) {
        setActiveRepoId(resolvedId);
      }
      setIsCompleted(true);
      setCurrentStageId('workspace_ready');
      setProgress(100);
      setStatusMessage('Your code universe is ready.');
      setStageStatuses((prev) => {
        const completedAll = {};
        for (const s of PIPELINE_STAGES) {
          completedAll[s.id] = 'completed';
        }
        return completedAll;
      });

      // Fetch genuine parsed statistics from backend
      let realNodeLabel = 'Analyzed';
      let realEdgeLabel = 'Analyzed';
      let detectedTech = [];

      try {
        if (resolvedId) {
          const liveGraph = await getRepositoryGraph(resolvedId);
          if (liveGraph?.nodes?.length) {
            realNodeLabel = `${liveGraph.nodes.length} nodes`;
            realEdgeLabel = `${liveGraph.edges?.length || 0} edges`;

            const rawLangs = liveGraph.nodes
              .map((n) => n.language)
              .filter((l) => l && l !== 'Unknown' && l !== 'Markdown');
            detectedTech = Array.from(new Set(rawLangs));
          }
        }
      } catch (err) {
        console.warn('Could not inspect completed graph metadata:', err);
      }

      if (detectedTech.length === 0) {
        detectedTech = ['Source Code'];
      }

      // Save repository to user's account with actual extracted facts
      if (user && (repoUrl || resolvedId)) {
        const now = new Date();
        const dateFormatted = `${now.getDate()} ${now.toLocaleString('default', { month: 'short' })} ${now.getFullYear()}, ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
        saveUserSingleRepository(user, {
          id: resolvedId || `repo-${Date.now()}`,
          repository_id: resolvedId,
          name: nameParam || repoMeta.fullName,
          url: repoUrl || `upload://${repoMeta.name}`,
          type: 'Public',
          desc: `${realNodeLabel} · ${realEdgeLabel} mapped into 2D and 3D space.`,
          tech: detectedTech,
          nodes: realNodeLabel,
          edges: realEdgeLabel,
          status: 'done',
          statusText: 'Analysis complete',
          real_metrics: true,
          lastAnalysed: dateFormatted,
          createdAtTimestamp: Date.now()
        });
      }
    }

    startPipeline();

    return () => {
      isCancelled = true;
      if (eventSource) eventSource.close();
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [repoUrl, repoIdParam, jobIdParam, nameParam, repoMeta.fullName, repoMeta.branch, user]);

  // Automatic smooth transition timer once workspace is confirmed ready
  useEffect(() => {
    if (!isCompleted) return;
    const targetRepoParam = activeRepoId || repoIdParam || repoUrl;
    const timer = setInterval(() => {
      setAutoCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          navigate(`/workspace?repo=${encodeURIComponent(targetRepoParam)}&name=${encodeURIComponent(nameParam || repoMeta.fullName)}&url=${encodeURIComponent(repoUrl)}`);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [isCompleted, navigate, activeRepoId, repoIdParam, repoUrl, nameParam, repoMeta.fullName]);

  const handleEnterWorkspace = () => {
    const targetRepoParam = activeRepoId || repoIdParam || repoUrl;
    navigate(`/workspace?repo=${encodeURIComponent(targetRepoParam)}&name=${encodeURIComponent(nameParam || repoMeta.fullName)}&url=${encodeURIComponent(repoUrl)}`);
  };

  const handleRetry = () => {
    setErrorMessage('');
    window.location.reload();
  };

  return (
    <div className="analyze-page">
      {/* Deep Space Horizon Atmosphere */}
      <div className="analyze-backdrop">
        <div className="analyze-ambient-top" />
        <div className="analyze-planet-glow" />
      </div>

      {/* Header Bar */}
      <header className="analyze-header">
        <div
          className="analyze-brand"
          onClick={() => navigate('/dashboard')}
          role="button"
          tabIndex={0}
        >
          <RingedPlanetLogo className="h-7 w-auto text-[#FB923C]" />
          <div className="analyze-brand-text">
            <span className="analyze-brand-title">A S T R O G R A P H</span>
            <span className="analyze-brand-sub">Repository Intelligence</span>
          </div>
        </div>

        {/* Live Repository Info Pill Panel */}
        <div className="analyze-repo-pill-card">
          <div className="repo-info-unit">
            <span className="repo-info-label">Repo:</span>
            <span className="repo-info-val">{repoMeta.fullName}</span>
          </div>
          <span className="text-gray-600">·</span>
          <div className="repo-info-unit">
            <span className="repo-info-label">Branch:</span>
            <span className="repo-branch-chip">
              <GitBranch size={11} /> {repoMeta.branch}
            </span>
          </div>
          <span className="text-gray-600">·</span>
          <div className="repo-info-unit">
            <span
              className={`repo-status-badge ${
                isCompleted
                  ? 'status-badge--ready'
                  : errorMessage
                  ? 'status-badge--failed'
                  : 'status-badge--processing'
              }`}
            >
              {!isCompleted && !errorMessage && <span className="pulse-beacon" />}
              {isCompleted ? 'INDEXED READY' : errorMessage ? 'ANALYSIS HALTED' : 'ANALYZING REPOSITORY'}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={() => navigate('/dashboard')}
          className="analyze-dashboard-btn"
          title="Return to Dashboard and Profile"
        >
          <Home size={14} className="analyze-dashboard-icon" />
          <span>Dashboard</span>
        </button>
      </header>

      {/* Main Analysis Container */}
      <main className="analyze-container">
        
        {/* Main Heading & Current Stage */}
        <section className="analyze-hero">
          <span className="analyze-eyebrow">
            [ REAL-TIME CELESTIAL ANALYSIS ENGINE ]
          </span>

          <h1 className="analyze-title">
            Mapping your code <em>universe.</em>
          </h1>

          <p className="analyze-sub">
            Tracing structure, discovering relationships, and preparing your repository for exploration.
          </p>

          {/* Prominent Current Stage Callout Banner */}
          <div className="current-stage-card">
            <span className="pulse-beacon" />
            <span className="stage-callout-text">{statusMessage}</span>
            <span className="stage-callout-pct">{progress}%</span>
          </div>
        </section>

        {/* Error Diagnostic Panel (if failure occurs) */}
        {errorMessage && (
          <div className="analyze-error-panel">
            <div className="error-title-row">
              <AlertTriangle size={18} />
              <span>Analysis Encountered an Issue</span>
            </div>
            <p className="text-sm text-gray-300">{errorMessage}</p>
            <div className="error-actions-row">
              <button
                type="button"
                onClick={handleRetry}
                className="error-action-btn error-action-btn--primary"
              >
                <RefreshCw size={14} /> Retry Analysis
              </button>
              <button
                type="button"
                onClick={() => navigate('/dashboard')}
                className="error-action-btn error-action-btn--secondary"
              >
                <ArrowLeft size={14} /> Back to Repository Input
              </button>
            </div>
          </div>
        )}

        {/* Central Visualization Stage */}
        <section className="analyze-vis-wrapper">
          <PipelineGalaxyCanvas stage={currentStageId} progress={progress} isComplete={isCompleted} />

          {/* Galaxy Ready Cinematic Overlay Banner */}
          {isCompleted && (
            <div className="vis-ready-overlay">
              <div className="w-11 h-11 rounded-full bg-[#FB923C]/20 border border-[#FB923C]/40 flex items-center justify-center text-[#FB923C] mb-1">
                <Sparkles size={22} />
              </div>
              <h2 className="vis-ready-heading">
                Your code <em>universe</em> is ready.
              </h2>
              <p className="vis-ready-sub">
                Your repository has been mapped. Start exploring its architecture, classes, and dependencies in 3D.
              </p>
              <button
                type="button"
                onClick={handleEnterWorkspace}
                className="vis-cta-btn"
              >
                <span>Enter the Galaxy</span>
                <ArrowRight size={17} />
              </button>
              <span className="vis-cta-auto-countdown">
                Auto-transitioning in {autoCountdown}s...
              </span>
            </div>
          )}
        </section>

        {/* 3-Column Pipeline Lower Section */}
        <section className="analyze-tri-grid">
          
          {/* Left Column: 9-Stage Step Tracker */}
          <div className="panel-card">
            <div className="panel-header-row">
              <div className="panel-title-wrap">
                <Layers size={14} className="text-[#FB923C]" />
                <h3 className="panel-title">Pipeline Stages</h3>
              </div>
              <span className="panel-chip-counter">
                {Object.values(stageStatuses).filter((s) => s === 'completed').length} / 9
              </span>
            </div>

            <div className="stages-list">
              {PIPELINE_STAGES.map((s) => {
                const status = stageStatuses[s.id] || 'pending';
                return (
                  <div
                    key={s.id}
                    className={`stage-item ${
                      status === 'running'
                        ? 'stage-item--running'
                        : status === 'completed'
                        ? 'stage-item--completed'
                        : status === 'failed'
                        ? 'stage-item--failed'
                        : ''
                    }`}
                  >
                    <div className="stage-status-icon-wrap">
                      {status === 'completed' ? (
                        <CheckCircle2 size={16} className="text-emerald-400" />
                      ) : status === 'running' ? (
                        <div className="pulse-beacon" />
                      ) : status === 'failed' ? (
                        <AlertTriangle size={15} className="text-red-400" />
                      ) : (
                        <div className="w-2.5 h-2.5 rounded-full border border-gray-600 bg-gray-800" />
                      )}
                    </div>

                    <div className="stage-body">
                      <span className="stage-name">{s.name}</span>
                      <span className="stage-subtext">{s.subtext}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Center Column: Telemetry Terminal */}
          <div className="panel-card">
            <div className="panel-header-row">
              <div className="panel-title-wrap">
                <Terminal size={14} className="text-[#FB923C]" />
                <h3 className="panel-title">Telemetry Terminal</h3>
              </div>

              <div className="terminal-controls">
                <button
                  type="button"
                  onClick={() => setIsAutoScroll(!isAutoScroll)}
                  className={`terminal-control-btn ${isAutoScroll ? 'terminal-control-btn--active' : ''}`}
                  title={isAutoScroll ? 'Pause Auto-Scroll' : 'Resume Auto-Scroll'}
                >
                  {isAutoScroll ? <Pause size={10} /> : <Play size={10} />}
                  <span>{isAutoScroll ? 'Auto-scroll' : 'Paused'}</span>
                </button>

                <button
                  type="button"
                  onClick={handleCopyLogs}
                  className="terminal-control-btn"
                  title="Copy Logs"
                >
                  {copiedLogs ? <Check size={10} className="text-emerald-400" /> : <Copy size={10} />}
                  <span>{copiedLogs ? 'Copied' : 'Copy'}</span>
                </button>

                <button
                  type="button"
                  onClick={() => setIsTerminalExpanded(!isTerminalExpanded)}
                  className="terminal-control-btn"
                  title={isTerminalExpanded ? 'Collapse' : 'Expand'}
                >
                  {isTerminalExpanded ? <Minimize2 size={10} /> : <Maximize2 size={10} />}
                </button>
              </div>
            </div>

            <div
              ref={logBoxRef}
              className={`terminal-log-box ${isTerminalExpanded ? 'terminal-log-box--expanded' : ''}`}
            >
              {logs.length === 0 ? (
                <div className="text-gray-500 italic p-2">Initializing streaming telemetry...</div>
              ) : (
                logs.map((log, idx) => {
                  const levelClass =
                    log.level === 'INGEST'
                      ? 'log-badge--ingest'
                      : log.level === 'SCAN' || log.level === 'EXTRACT'
                      ? 'log-badge--scan'
                      : log.level === 'AST'
                      ? 'log-badge--ast'
                      : log.level === 'DEPENDENCY'
                      ? 'log-badge--dependency'
                      : log.level === 'GRAPH'
                      ? 'log-badge--graph'
                      : log.level === 'METRICS'
                      ? 'log-badge--metrics'
                      : log.level === 'AI'
                      ? 'log-badge--ai'
                      : log.level === 'RENDER'
                      ? 'log-badge--render'
                      : log.level === 'READY'
                      ? 'log-badge--ready'
                      : log.level === 'ERROR'
                      ? 'log-badge--error'
                      : 'log-badge--ingest';

                  return (
                    <div key={idx} className="log-entry-row">
                      <span className="log-timestamp">{log.timestamp}</span>
                      <span className={`log-badge ${levelClass}`}>[{log.level}]</span>
                      <span
                        className={`log-text ${
                          log.level === 'READY'
                            ? 'log-text--ready'
                            : log.level === 'ERROR'
                            ? 'log-text--error'
                            : ''
                        }`}
                      >
                        {log.text}
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Right Column: Live Metrics Panel */}
          <div className="panel-card">
            <div className="panel-header-row">
              <div className="panel-title-wrap">
                <Cpu size={14} className="text-[#FB923C]" />
                <h3 className="panel-title">Graph Metrics</h3>
              </div>
              <span className="panel-chip-counter">Live</span>
            </div>

            <div className="metrics-stack-grid">
              <div className="metric-tile">
                <span className="metric-val metric-val--cyan">
                  {metrics.filesDiscovered !== null ? metrics.filesDiscovered : '—'}
                </span>
                <span className="metric-label">Files Discovered</span>
              </div>

              <div className="metric-tile">
                <span className="metric-val metric-val--emerald">
                  {metrics.filesParsed !== null ? metrics.filesParsed : '—'}
                </span>
                <span className="metric-label">Files Parsed</span>
              </div>

              <div className="metric-tile">
                <span className="metric-val metric-val--accent">
                  {metrics.symbolsExtracted !== null ? metrics.symbolsExtracted : '—'}
                </span>
                <span className="metric-label">Symbols Extracted</span>
              </div>

              <div className="metric-tile">
                <span className="metric-val metric-val--peach">
                  {metrics.dependencyEdges !== null ? metrics.dependencyEdges : '—'}
                </span>
                <span className="metric-label">Dependency Edges</span>
              </div>

              <div className="metric-tile">
                <span className="metric-val">
                  {metrics.graphNodes !== null ? metrics.graphNodes : '—'}
                </span>
                <span className="metric-label">Graph Nodes</span>
              </div>

              <div className="metric-tile">
                <span className="metric-val metric-val--accent">
                  {metrics.communitiesDetected !== null ? metrics.communitiesDetected : '—'}
                </span>
                <span className="metric-label">Communities</span>
              </div>
            </div>

            <div className="metrics-footer-timer">
              <span>Pipeline Elapsed Time</span>
              <span className="timer-digits">
                {String(Math.floor(elapsedSeconds / 60)).padStart(2, '0')}:
                {String(elapsedSeconds % 60).padStart(2, '0')}s
              </span>
            </div>
          </div>

        </section>

      </main>

      {/* Shared Global Site Footer */}
      <SiteFooter />
    </div>
  );
}
