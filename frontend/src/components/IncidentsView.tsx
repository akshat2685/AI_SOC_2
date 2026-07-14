'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useStore, Incident } from '@/store/useStore';
import { api } from '@/lib/api';
import { 
  AlertTriangle, 
  CheckCircle, 
  Clock, 
  Sparkles, 
  Send,
  Zap,
  Lock,
  UserX,
  FileSpreadsheet,
  Search,
  Brain,
  Shield,
  ChevronRight,
  FileText,
  Target,
  Eye,
  X,
  Loader2,
  Download,
  ChevronDown,
  Check,
  ShieldAlert,
  History,
  Globe,
  Activity
} from 'lucide-react';
import XAIPanel from './XAIPanel';
import MultiplayerCursor from './MultiplayerCursor';
import VoiceCommandBar from './VoiceCommandBar';
import QuickBlockModal from './QuickBlockModal';

type DetailTab = 'summary' | 'investigation' | 'timeline' | 'mitre' | 'soar';

interface SimilarIncident {
  id: number;
  title: string;
  similarityReason: string;
  verdict: string;
  resolvedAt: string | null;
}

interface ThreatIntel {
  hasMatch: boolean;
  source: string;
  threatActor: string;
  campaign: string;
  malwareFamily: string;
  matchedIndicator: string;
  severity: string;
  context: string;
}

interface RecommendedPlaybook {
  id: string;
  name: string;
  description: string;
  difficulty: 'Low' | 'Medium' | 'High';
  duration: string;
  matchReason: string;
  recommendedActions: string[];
}

interface RecommendedTriageData {
  incidentId: number;
  similarIncidents: SimilarIncident[];
  threatIntel: ThreatIntel;
  recommendedPlaybooks: RecommendedPlaybook[];
  timestamp: string;
}

export default function IncidentsView() {
  const { incidents, setIncidents, alerts, theme } = useStore();

  // Sparkline data calculation for last 24 hours
  const nowTime = Date.now();
  const startTime = nowTime - 24 * 3600 * 1000;
  const bins = Array(24).fill(0);
  let last24hCount = 0;

  incidents.forEach(inc => {
    const incTime = new Date(inc.timestamp).getTime();
    if (incTime >= startTime && incTime <= nowTime) {
      last24hCount++;
      const diffHours = Math.floor((incTime - startTime) / (3600 * 1000));
      if (diffHours >= 0 && diffHours < 24) {
        bins[diffHours]++;
      }
    }
  });

  const maxVal = Math.max(...bins, 1);
  const points = bins.map((val, idx) => {
    const x = (idx / 23) * 128;
    // Map value to heights between 4 and 32 to leave some padding
    const y = 32 - (val / maxVal) * 28;
    return { x, y };
  });

  const pathD = points.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  const areaD = `${pathD} L 128 36 L 0 36 Z`;
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [notes, setNotes] = useState('');
  const [updating, setUpdating] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [soarLog, setSoarLog] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<DetailTab>('summary');
  const [incidentDetails, setIncidentDetails] = useState<any>(null);
  const [investigation, setInvestigation] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [investigationLoading, setInvestigationLoading] = useState(false);
  const [predictedRisk, setPredictedRisk] = useState<any>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [recommendedTriage, setRecommendedTriage] = useState<RecommendedTriageData | null>(null);
  const [triageLoading, setTriageLoading] = useState(false);
  const [completedTriageSteps, setCompletedTriageSteps] = useState<string[]>([]);
  const [selectedSeverities, setSelectedSeverities] = useState<string[]>(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']);
  const [isSeverityDropdownOpen, setIsSeverityDropdownOpen] = useState(false);
  const severityDropdownRef = useRef<HTMLDivElement>(null);
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [blockingIp, setBlockingIp] = useState<string | null>(null);
  const [blockReason, setBlockReason] = useState<string>('');

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (severityDropdownRef.current && !severityDropdownRef.current.contains(event.target as Node)) {
        setIsSeverityDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const toggleSeverity = (severity: string) => {
    if (selectedSeverities.includes(severity)) {
      setSelectedSeverities(selectedSeverities.filter(s => s !== severity));
    } else {
      setSelectedSeverities([...selectedSeverities, severity]);
    }
  };

  const getSeverityButtonText = () => {
    if (selectedSeverities.length === 0) return 'No Severity';
    if (selectedSeverities.length === 4) return 'All Severities';
    if (selectedSeverities.length > 2) return `${selectedSeverities.length} Selected`;
    return selectedSeverities.map(s => s.charAt(0) + s.slice(1).toLowerCase()).join(', ');
  };

  const severityOptions = [
    { value: 'CRITICAL', label: 'Critical', color: 'bg-red-500' },
    { value: 'HIGH', label: 'High', color: 'bg-orange-500' },
    { value: 'MEDIUM', label: 'Medium', color: 'bg-amber-500' },
    { value: 'LOW', label: 'Low', color: 'bg-blue-500' },
  ];

  // Load incident details when selected
  useEffect(() => {
    if (!selectedIncident) return;
    setDetailLoading(true);
    api.getIncidentDetails(selectedIncident.id)
      .then(data => setIncidentDetails(data))
      .catch(e => console.error('Detail fetch failed:', e))
      .finally(() => setDetailLoading(false));
  }, [selectedIncident?.id]);

  // Load AI Predicted Risk when selected
  useEffect(() => {
    if (!selectedIncident) {
      setPredictedRisk(null);
      return;
    }
    setRiskLoading(true);
    setPredictedRisk(null);
    api.predictIncidentRisk(selectedIncident.id)
      .then(data => setPredictedRisk(data))
      .catch(e => console.error('Risk prediction fetch failed:', e))
      .finally(() => setRiskLoading(false));
  }, [selectedIncident?.id]);

  // Load AI Recommended Triage when selected
  useEffect(() => {
    if (!selectedIncident) {
      setRecommendedTriage(null);
      return;
    }
    setTriageLoading(true);
    setRecommendedTriage(null);
    api.getRecommendedTriage(selectedIncident.id)
      .then(data => setRecommendedTriage(data as RecommendedTriageData))
      .catch(e => console.error('Recommended triage fetch failed:', e))
      .finally(() => setTriageLoading(false));
  }, [selectedIncident?.id]);

  const handleSelectIncident = (inc: Incident) => {
    setSelectedIncident(inc);
    setNotes(inc.analyst_notes || '');
    setActiveTab('summary');
    setInvestigation(null);
    setIncidentDetails(null);
    setRecommendedTriage(null);
    setPredictedRisk(null);
    setCompletedTriageSteps([]);
  };

  const handleUpdateIncident = async (status: string, verdict: string) => {
    if (!selectedIncident) return;
    setUpdating(true);
    try {
      await api.updateIncident(selectedIncident.id, status, verdict, notes);
      const updated = await api.getIncidents();
      setIncidents(updated);
      setSelectedIncident(prev => prev ? { ...prev, status, verdict, analyst_notes: notes } : null);
      setSoarLog(prev => [`System: Updated incident ${selectedIncident.id} → ${status} (${verdict})`, ...prev]);
    } catch (e: any) {
      console.error(e);
    } finally {
      setUpdating(false);
    }
  };

  const handleRunInvestigation = async () => {
    if (!selectedIncident) return;
    setInvestigationLoading(true);
    setActiveTab('investigation');
    try {
      const taskDesc = `Investigate Incident ${selectedIncident.id}: ${selectedIncident.title}. Correlation key: ${selectedIncident.correlation_key}.`;
      const result = await api.triggerAgentTask(taskDesc);
      setInvestigation(result);
      setSoarLog(prev => [`Agent Team: Investigation complete for incident ${selectedIncident.id}`, ...prev]);
    } catch (e: any) {
      setInvestigation({ error: e.message, messages: [`Investigation triggered (backend may be offline): ${e.message}`] });
    } finally {
      setInvestigationLoading(false);
    }
  };

  const triggerSOAR = async (actionType: string) => {
    if (!selectedIncident) return;
    setActionLoading(actionType);
    setSoarLog(prev => [`SOAR: Triggered ${actionType} for incident ${selectedIncident.id}...`, ...prev]);
    try {
      await api.triggerAgentTask(`Trigger response playbook for Incident ${selectedIncident.id}. Action: ${actionType}.`);
      setSoarLog(prev => [`SOAR: ${actionType} execution initiated. Approval request sent.`, ...prev]);
    } catch (e: any) {
      setSoarLog(prev => [`SOAR: ${actionType} triggered (sandbox mock).`, ...prev]);
    } finally {
      setActionLoading(null);
    }
  };

  // Filtered incidents
  const filteredIncidents = incidents.filter(inc => {
    if (!selectedSeverities.includes(inc.severity)) return false;
    if (filterStatus !== 'ALL' && inc.status !== filterStatus) return false;
    
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      
      // 1. Direct fields
      if (inc.title.toLowerCase().includes(q)) return true;
      if (inc.correlation_key?.toLowerCase().includes(q)) return true;
      if (inc.llm_summary?.toLowerCase().includes(q)) return true;
      if (inc.status?.toLowerCase().includes(q)) return true;
      if (inc.verdict?.toLowerCase().includes(q)) return true;
      
      // 2. Associated Alerts fields (IP or threat/attack type)
      const hasMatchingAlert = alerts.some(alt => 
        alt.incident_id === inc.id && 
        (
          alt.attacker_ip?.toLowerCase().includes(q) || 
          alt.attack_type?.toLowerCase().includes(q) ||
          alt.title?.toLowerCase().includes(q)
        )
      );
      if (hasMatchingAlert) return true;
      
      return false;
    }
    
    return true;
  });

  const handleDownloadCSV = () => {
    if (filteredIncidents.length === 0) return;
    
    const headers = ['ID', 'Title', 'Severity', 'Status', 'Verdict', 'Correlation Key', 'Created At', 'Resolved At', 'Analyst Notes'];
    const rows = filteredIncidents.map(inc => [
      inc.id,
      `"${inc.title.replace(/"/g, '""')}"`,
      inc.severity,
      inc.status,
      inc.verdict || 'N/A',
      inc.correlation_key || '',
      inc.timestamp || '',
      inc.resolved_at || '',
      `"${(inc.analyst_notes || '').replace(/"/g, '""')}"`
    ]);

    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `incidents_export_${new Date().toISOString().slice(0, 10)}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const getStateTransitions = (inc: Incident) => {
    const baseTime = new Date(inc.timestamp).getTime();
    
    return [
      {
        phase: 'Detected',
        title: 'Threat Detected',
        description: `Incident identified with ${inc.severity} severity.`,
        timestamp: new Date(baseTime).toLocaleString(),
        status: 'completed',
        icon: AlertTriangle,
        color: 'border-red-500/30 bg-red-950/20 text-red-400',
        dotColor: 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]',
        details: [
          `Severity: ${inc.severity}`,
          `Target key: ${inc.correlation_key || 'N/A'}`,
          'Source: Behavioral telemetry'
        ]
      },
      {
        phase: 'Enriched',
        title: 'Triage & Enrichment',
        description: 'Automated IOC matching and MITRE ATT&CK mapping.',
        timestamp: new Date(baseTime + 120000).toLocaleString(),
        status: 'completed',
        icon: Search,
        color: 'border-blue-500/30 bg-blue-950/20 text-blue-400',
        dotColor: 'bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.5)]',
        details: [
          'CTI Threat Intelligence correlation completed',
          `Related alerts mapped: ${incidentDetails?.alerts?.length || 0}`
        ]
      },
      {
        phase: 'Investigated',
        title: inc.status !== 'OPEN' || investigation ? 'AI Investigation Complete' : 'AI Analysis Active',
        description: inc.status !== 'OPEN' || investigation
          ? 'Deep behavioral profiling completed by Agent Team.' 
          : 'Pending analyst-triggered deep investigation.',
        timestamp: new Date(baseTime + 300000).toLocaleString(),
        status: inc.status !== 'OPEN' || investigation ? 'completed' : 'active',
        icon: Brain,
        color: inc.status !== 'OPEN' || investigation ? 'border-indigo-500/30 bg-indigo-950/20 text-indigo-400' : 'border-slate-800 bg-slate-900/10 text-slate-500',
        dotColor: inc.status !== 'OPEN' || investigation ? 'bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.5)]' : 'bg-slate-700 animate-pulse',
        details: inc.llm_summary 
          ? [inc.llm_summary.slice(0, 150) + (inc.llm_summary.length > 150 ? '...' : '')] 
          : ['Awaiting multi-agent analysis pipeline trigger.']
      },
      {
        phase: 'Contained',
        title: completedTriageSteps.length > 0 || inc.status === 'RESOLVED' ? 'Incident Contained' : 'Containment Pending',
        description: completedTriageSteps.length > 0 || inc.status === 'RESOLVED'
          ? 'Playbook actions successfully executed.'
          : 'Awaiting playbook triggering via SOAR tab.',
        timestamp: new Date(baseTime + 600000).toLocaleString(),
        status: inc.status === 'RESOLVED' ? 'completed' : completedTriageSteps.length > 0 ? 'active' : 'pending',
        icon: Zap,
        color: inc.status === 'RESOLVED' ? 'border-emerald-500/30 bg-emerald-950/20 text-emerald-400' : completedTriageSteps.length > 0 ? 'border-amber-500/30 bg-amber-950/20 text-amber-400' : 'border-slate-900 bg-slate-950/10 text-slate-600',
        dotColor: inc.status === 'RESOLVED' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : completedTriageSteps.length > 0 ? 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]' : 'bg-slate-800',
        details: completedTriageSteps.length > 0 
          ? [`Executed ${completedTriageSteps.length} containment check-list actions.`] 
          : ['Response playbooks available in SOAR panel.']
      },
      {
        phase: 'Resolved',
        title: inc.status === 'RESOLVED' ? 'Incident Resolved' : 'Resolution Sign-off Pending',
        description: inc.status === 'RESOLVED' 
          ? `Verdict confirmed as ${inc.verdict || 'TRUE_POSITIVE'}.` 
          : 'Awaiting final verification and post-mortem.',
        timestamp: inc.resolved_at ? new Date(inc.resolved_at).toLocaleString() : new Date(baseTime + 900000).toLocaleString(),
        status: inc.status === 'RESOLVED' ? 'completed' : 'pending',
        icon: CheckCircle,
        color: inc.status === 'RESOLVED' ? 'border-emerald-500/30 bg-emerald-950/20 text-emerald-400' : 'border-slate-900 bg-slate-950/10 text-slate-600',
        dotColor: inc.status === 'RESOLVED' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-slate-800',
        details: inc.analyst_notes 
          ? [`Notes: ${inc.analyst_notes}`] 
          : ['Click "TP Resolve" or "FP Dismiss" in header to close case.']
      }
    ];
  };

  const tabs: { id: DetailTab; label: string; icon: React.ElementType }[] = [
    { id: 'summary', label: 'Summary', icon: Eye },
    { id: 'investigation', label: 'AI Investigation', icon: Brain },
    { id: 'timeline', label: 'Timeline', icon: Clock },
    { id: 'mitre', label: 'MITRE', icon: Target },
    { id: 'soar', label: 'SOAR', icon: Zap },
  ];

  return (
    <div className="p-6 h-[calc(100vh-4rem)] flex flex-col gap-4 overflow-hidden">
      {selectedIncident && <MultiplayerCursor incidentId={selectedIncident.id.toString()} />}

      {/* IncidentsView Header with Real-time Client-side Filter */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/50 border border-slate-800 rounded-xl p-4 flex-shrink-0 shadow-lg">
        <div>
          <h2 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
            <Shield className="w-4 h-4 text-blue-500" /> Security Incidents Command Center
          </h2>
          <p className="text-[10px] text-slate-400 mt-1">
            Real-time telemetry monitoring, automated response playbooks, and AI incident triage workbench.
          </p>
        </div>

        {/* Real-time Incident Sparkline */}
        <div className="hidden lg:flex items-center gap-4 bg-slate-950/40 border border-slate-800/60 px-4 py-2 rounded-xl">
          <div className="text-left">
            <div className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">24h Incident Volume</div>
            <div className="flex items-baseline gap-1">
              <span className="text-lg font-mono font-bold text-slate-200">{last24hCount}</span>
              <span className="text-[9px] text-slate-500 font-medium">total</span>
            </div>
          </div>
          <div className="w-32 h-10 relative flex items-center">
            <svg viewBox="0 0 128 36" className="w-full h-full overflow-visible">
              <defs>
                <linearGradient id="sparklineGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={theme === 'light' ? '#2563eb' : '#3b82f6'} stopOpacity="0.4" />
                  <stop offset="100%" stopColor={theme === 'light' ? '#2563eb' : '#3b82f6'} stopOpacity="0.0" />
                </linearGradient>
              </defs>
              <path
                d={areaD}
                fill="url(#sparklineGrad)"
              />
              <path
                d={pathD}
                fill="none"
                stroke={theme === 'light' ? '#2563eb' : '#3b82f6'}
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {points.length > 0 && (
                <>
                  <circle
                    cx={points[points.length - 1].x}
                    cy={points[points.length - 1].y}
                    r="2.5"
                    fill={theme === 'light' ? '#2563eb' : '#3b82f6'}
                  />
                  <circle
                    cx={points[points.length - 1].x}
                    cy={points[points.length - 1].y}
                    r="4.5"
                    fill="none"
                    stroke={theme === 'light' ? '#2563eb' : '#3b82f6'}
                    strokeWidth="1"
                    className="animate-pulse"
                  />
                </>
              )}
            </svg>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative w-64 md:w-80">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
            <input
              type="text"
              id="incidents-header-filter"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Filter by IP, threat/attack type, title, key..."
              className="w-full bg-slate-950/60 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-xs focus:outline-none focus:border-blue-500/50 text-slate-200 placeholder:text-slate-600"
            />
          </div>
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 flex gap-6 overflow-hidden min-h-0">
        {/* Left Panel — Incidents List */}
        <div className="w-[380px] flex-shrink-0 bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden shadow-lg flex flex-col h-full">
        {/* Filters */}
        <div className="px-4 py-3 border-b border-slate-800 space-y-2 flex-shrink-0">
          <div className="flex justify-between items-center">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">Incidents</h3>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleDownloadCSV}
                title="Download CSV"
                className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200 transition-colors flex items-center gap-1 text-[10px] font-semibold cursor-pointer"
              >
                <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-500" />
                <span>Export</span>
              </button>
              <span className="text-[10px] bg-slate-800 px-2 py-0.5 rounded-full font-bold text-slate-300">
                {filteredIncidents.length}/{incidents.length}
              </span>
            </div>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search incidents..."
              className="w-full bg-slate-950/60 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-[11px] focus:outline-none focus:border-blue-500/50 text-slate-200 placeholder:text-slate-600"
            />
          </div>
          <div className="flex gap-2">
            <div className="relative flex-1" ref={severityDropdownRef}>
              <button
                type="button"
                onClick={() => setIsSeverityDropdownOpen(!isSeverityDropdownOpen)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-[10px] text-slate-300 focus:outline-none flex justify-between items-center gap-1.5 hover:border-slate-700 transition-all cursor-pointer text-left h-full min-h-[26px]"
              >
                <span className="truncate">{getSeverityButtonText()}</span>
                <ChevronDown className={`w-3 h-3 text-slate-400 flex-shrink-0 transition-transform ${isSeverityDropdownOpen ? 'rotate-180' : ''}`} />
              </button>

              {isSeverityDropdownOpen && (
                <div className="absolute left-0 mt-1 w-56 bg-slate-950 border border-slate-800 rounded-lg shadow-2xl z-30 py-1.5 text-[10px] animate-in fade-in duration-100">
                  <div className="flex items-center justify-between px-3 py-1 border-b border-slate-800/80 text-[9px] text-slate-400 mb-1">
                    <span className="font-semibold uppercase tracking-wider">Severity</span>
                    <div className="flex gap-2">
                      <button 
                        type="button" 
                        onClick={() => setSelectedSeverities(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'])}
                        className="hover:text-blue-400 font-bold uppercase transition-all"
                      >
                        All
                      </button>
                      <button 
                        type="button" 
                        onClick={() => setSelectedSeverities([])}
                        className="hover:text-rose-400 font-bold uppercase transition-all"
                      >
                        None
                      </button>
                    </div>
                  </div>
                  <div className="space-y-0.5">
                    {severityOptions.map(opt => {
                      const isChecked = selectedSeverities.includes(opt.value);
                      return (
                        <button
                          key={opt.value}
                          type="button"
                          onClick={() => toggleSeverity(opt.value)}
                          className="w-full px-3 py-1.5 hover:bg-slate-900 text-left flex items-center justify-between transition-colors group cursor-pointer"
                        >
                          <div className="flex items-center gap-2">
                            <span className={`w-1.5 h-1.5 rounded-full ${opt.color}`} />
                            <span className="text-slate-300 font-medium group-hover:text-white transition-colors">
                              {opt.label}
                            </span>
                          </div>
                          <div className={`w-3.5 h-3.5 rounded border flex items-center justify-center transition-all ${
                            isChecked 
                              ? 'bg-blue-600 border-blue-500 text-white' 
                              : 'border-slate-800 group-hover:border-slate-700 bg-slate-950'
                          }`}>
                            {isChecked && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
            <select 
              value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
              className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-[10px] text-slate-300 focus:outline-none"
            >
              <option value="ALL">All Status</option>
              <option value="OPEN">Open</option>
              <option value="INVESTIGATING">Investigating</option>
              <option value="RESOLVED">Resolved</option>
            </select>
          </div>
        </div>

        {/* Incident List */}
        <div className="flex-1 overflow-y-auto divide-y divide-slate-800/50">
          {filteredIncidents.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-2">
              <CheckCircle className="w-8 h-8 opacity-40 text-emerald-400" />
              <span className="text-xs">No matching incidents found.</span>
            </div>
          ) : (
            filteredIncidents.map(inc => {
              const active = selectedIncident?.id === inc.id;
              return (
                <div 
                  key={inc.id}
                  onClick={() => handleSelectIncident(inc)}
                  className={`p-4 cursor-pointer hover:bg-slate-800/20 transition-all ${
                    active ? 'bg-blue-950/20 border-l-2 border-blue-500' : 'border-l-2 border-transparent'
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <span className="text-xs font-semibold text-slate-200 block truncate max-w-[220px]">{inc.title}</span>
                    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-md flex-shrink-0 ${
                      inc.severity === 'CRITICAL' 
                        ? 'bg-red-950/40 text-red-400 border border-red-800/30' 
                        : inc.severity === 'HIGH'
                        ? 'bg-orange-950/40 text-orange-400 border border-orange-800/30'
                        : 'bg-amber-950/40 text-amber-400 border border-amber-800/30'
                    }`}>
                      {inc.severity}
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-500 mt-1 font-mono truncate">{inc.correlation_key}</p>
                  <div className="flex justify-between items-center mt-2">
                    <div className="flex gap-1.5 items-center">
                      <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${
                        inc.status === 'RESOLVED' 
                          ? 'bg-emerald-950/40 text-emerald-400 border border-emerald-800/30' 
                          : 'bg-blue-950/40 text-blue-400 border border-blue-800/30'
                      }`}>
                        {inc.status}
                      </span>
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full flex items-center gap-0.5 ${
                        inc.severity === 'CRITICAL'
                          ? 'bg-red-950/30 text-red-400 border border-red-900/20'
                          : inc.severity === 'HIGH'
                          ? 'bg-orange-950/30 text-orange-400 border border-orange-900/20'
                          : inc.severity === 'MEDIUM'
                          ? 'bg-amber-950/30 text-amber-400 border border-amber-900/20'
                          : 'bg-blue-950/30 text-blue-400 border border-blue-900/20'
                      }`}>
                        <Sparkles className="w-2.5 h-2.5" />
                        Risk: {inc.severity === 'CRITICAL' ? '85%' : inc.severity === 'HIGH' ? '65%' : inc.severity === 'MEDIUM' ? '45%' : '25%'}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-600">{new Date(inc.timestamp).toLocaleDateString()}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Right Panel — Detail Workbench */}
      <div className="flex-1 bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden shadow-lg flex flex-col h-full">
        {selectedIncident ? (
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Header with actions */}
            <div className="px-6 py-4 border-b border-slate-800 flex justify-between items-center flex-shrink-0">
              <div className="min-w-0">
                <h2 className="text-sm font-bold text-slate-200 truncate">{selectedIncident.title}</h2>
                <p className="text-[10px] text-slate-400 mt-0.5">
                  ID: <span className="font-mono text-slate-300">#{selectedIncident.id}</span> • 
                  Key: <span className="font-mono text-slate-300">{selectedIncident.correlation_key}</span>
                </p>
              </div>
              <div className="flex gap-2 flex-shrink-0">
                <button
                  onClick={handleRunInvestigation}
                  disabled={investigationLoading}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-3 py-1.5 rounded-lg text-xs transition-all flex items-center gap-1.5 shadow-lg shadow-indigo-900/20"
                >
                  {investigationLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Brain className="w-3 h-3" />}
                  Investigate
                </button>
                <button
                  onClick={() => handleUpdateIncident('RESOLVED', 'TRUE_POSITIVE')}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-3 py-1.5 rounded-lg text-xs transition-all"
                  disabled={updating}
                >
                  TP Resolve
                </button>
                <button
                  onClick={() => handleUpdateIncident('RESOLVED', 'FALSE_POSITIVE')}
                  className="bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 font-semibold px-3 py-1.5 rounded-lg text-xs transition-all"
                  disabled={updating}
                >
                  FP Dismiss
                </button>
              </div>
            </div>

            {/* Tab Navigation */}
            <div className="px-6 border-b border-slate-800 flex gap-1 flex-shrink-0">
              {tabs.map(tab => {
                const Icon = tab.icon;
                const active = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-1.5 px-3 py-2.5 text-[10px] font-bold uppercase tracking-wider transition-all border-b-2 ${
                      active 
                        ? 'text-blue-400 border-blue-500' 
                        : 'text-slate-500 border-transparent hover:text-slate-300'
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {tab.label}
                  </button>
                );
              })}
            </div>

            {/* Tab Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-5">
              
              {/* SUMMARY TAB */}
              {activeTab === 'summary' && (
                <>
                  {/* AI Summary */}
                  <div className="bg-gradient-to-r from-slate-950 to-indigo-950/20 border border-indigo-900/20 rounded-xl p-5 relative overflow-hidden">
                    <div className="flex items-center gap-2 mb-3">
                      <Sparkles className="w-4 h-4 text-indigo-400" />
                      <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">AI Investigation Summary</h4>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      {selectedIncident.llm_summary || "No AI analysis available yet. Click 'Investigate' to trigger the multi-agent investigation pipeline."}
                    </p>
                  </div>

                  {/* Incident Metadata Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {[
                      { label: 'Severity', value: selectedIncident.severity, color: selectedIncident.severity === 'CRITICAL' ? 'text-red-400' : 'text-amber-400' },
                      { label: 'Status', value: selectedIncident.status, color: selectedIncident.status === 'RESOLVED' ? 'text-emerald-400' : 'text-blue-400' },
                      { label: 'Verdict', value: selectedIncident.verdict || 'PENDING', color: 'text-slate-300' },
                      { label: 'Created', value: new Date(selectedIncident.timestamp).toLocaleString(), color: 'text-slate-300' },
                    ].map((item, idx) => (
                      <div key={idx} className="bg-slate-950/60 border border-slate-800 rounded-lg p-3">
                        <p className="text-[9px] text-slate-500 font-bold uppercase tracking-wider">{item.label}</p>
                        <p className={`text-xs font-bold mt-1 ${item.color}`}>{item.value}</p>
                      </div>
                    ))}
                  </div>

                  {/* Predicted Risk Estimation */}
                  <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-5 space-y-4">
                    <div className="flex justify-between items-center">
                      <div className="flex items-center gap-2">
                        <ShieldAlert className="w-4 h-4 text-rose-400" />
                        <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">AI Predicted Escalation Risk</h4>
                      </div>
                      
                      {riskLoading ? (
                        <div className="flex items-center gap-1.5 text-[10px] text-slate-500 font-semibold">
                          <Loader2 className="w-3 h-3 animate-spin text-indigo-400" /> Assessing risk...
                        </div>
                      ) : predictedRisk ? (
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider flex items-center gap-1 border ${
                            predictedRisk.riskLevel === 'Critical'
                              ? 'bg-red-950/40 text-red-400 border-red-900/40'
                              : predictedRisk.riskLevel === 'High'
                              ? 'bg-orange-950/40 text-orange-400 border-orange-900/40'
                              : predictedRisk.riskLevel === 'Medium'
                              ? 'bg-amber-950/40 text-amber-400 border-amber-900/40'
                              : 'bg-blue-950/40 text-blue-400 border-blue-900/40'
                          }`}>
                            {predictedRisk.riskLevel} Escalation Risk ({predictedRisk.likelihood})
                          </span>
                        </div>
                      ) : null}
                    </div>

                    {riskLoading ? (
                      <div className="space-y-2 py-2">
                        <div className="h-2.5 bg-slate-800 rounded animate-pulse w-3/4"></div>
                        <div className="h-2 bg-slate-800 rounded animate-pulse w-5/6"></div>
                      </div>
                    ) : predictedRisk ? (
                      <div className="space-y-3">
                        <div className="flex items-center gap-3">
                          <div className="w-full bg-slate-900 rounded-full h-2.5 overflow-hidden border border-slate-800/80">
                            <div 
                              className={`h-full rounded-full transition-all duration-1000 ${
                                predictedRisk.riskScore >= 75
                                  ? 'bg-gradient-to-r from-red-600 to-rose-500'
                                  : predictedRisk.riskScore >= 50
                                  ? 'bg-gradient-to-r from-orange-500 to-amber-500'
                                  : 'bg-gradient-to-r from-blue-500 to-emerald-500'
                              }`}
                              style={{ width: `${predictedRisk.riskScore}%` }}
                            />
                          </div>
                          <span className="text-[10px] font-bold text-slate-400 flex-shrink-0 font-mono">
                            {predictedRisk.riskScore}/100 Score
                          </span>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                          <div className="bg-slate-900/40 border border-slate-850 p-3 rounded-lg space-y-1">
                            <p className="text-[9px] text-slate-500 font-bold uppercase tracking-wider">Risk Reasoning</p>
                            <p className="text-[11px] text-slate-300 font-medium leading-relaxed">
                              {predictedRisk.reasoning}
                            </p>
                          </div>
                          <div className="bg-slate-900/40 border border-slate-850 p-3 rounded-lg space-y-1">
                            <p className="text-[9px] text-slate-500 font-bold uppercase tracking-wider">AI Mitigation Action Plan</p>
                            <p className="text-[11px] text-slate-300 font-medium leading-relaxed">
                              {predictedRisk.mitigation}
                            </p>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <p className="text-[10px] text-slate-500 italic">Failed to calculate risk indicators. Try selecting another incident.</p>
                    )}
                  </div>

                  {/* Recommended Triage Section */}
                  <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-5 space-y-5">
                    <div className="flex justify-between items-center border-b border-slate-800/60 pb-3">
                      <div className="flex items-center gap-2">
                        <Activity className="w-4 h-4 text-emerald-400" />
                        <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">Recommended Triage Plan</h4>
                        <span className="text-[9px] bg-emerald-950/60 text-emerald-400 border border-emerald-800/30 px-1.5 py-0.5 rounded-md font-semibold flex items-center gap-1">
                          <Sparkles className="w-2.5 h-2.5" /> AI Recommended
                        </span>
                      </div>
                      
                      {triageLoading && (
                        <div className="flex items-center gap-1.5 text-[10px] text-slate-500 font-semibold">
                          <Loader2 className="w-3 h-3 animate-spin text-emerald-400" /> Correlating intelligence...
                        </div>
                      )}
                    </div>

                    {triageLoading ? (
                      <div className="space-y-3 py-2">
                        <div className="h-3 bg-slate-800 rounded animate-pulse w-2/3"></div>
                        <div className="h-2 bg-slate-800 rounded animate-pulse w-full"></div>
                        <div className="h-2 bg-slate-800 rounded animate-pulse w-4/5"></div>
                      </div>
                    ) : recommendedTriage ? (
                      <div className="space-y-5">
                        
                        {/* Threat Intelligence Row */}
                        {recommendedTriage.threatIntel && (
                          <div className="bg-slate-900/50 border border-slate-800/60 rounded-xl p-4 space-y-3 relative overflow-hidden">
                            <div className="absolute right-0 top-0 w-24 h-24 bg-rose-500/5 blur-2xl rounded-full" />
                            
                            <div className="flex justify-between items-start">
                              <div className="flex items-center gap-2">
                                <Globe className="w-4 h-4 text-rose-400" />
                                <span className="text-[10px] font-bold text-slate-300 uppercase tracking-wider">Threat Intelligence Correlation</span>
                              </div>
                              <span className="text-[9px] bg-rose-950/40 text-rose-400 border border-rose-900/30 px-2 py-0.5 rounded font-bold uppercase">
                                {recommendedTriage.threatIntel.severity || 'HIGH'} CTI MATCH
                              </span>
                            </div>

                            <p className="text-[11px] text-slate-300 leading-relaxed italic bg-slate-950/40 border border-slate-850 p-2.5 rounded-lg">
                              {recommendedTriage.threatIntel.context}
                            </p>

                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px]">
                              <div className="bg-slate-950/40 border border-slate-850 p-2 rounded-lg">
                                <span className="text-slate-500 block font-semibold uppercase text-[8px] tracking-wider">Threat Actor</span>
                                <span className="text-slate-300 font-bold">{recommendedTriage.threatIntel.threatActor || 'UNKNOWN'}</span>
                              </div>
                              <div className="bg-slate-950/40 border border-slate-850 p-2 rounded-lg">
                                <span className="text-slate-500 block font-semibold uppercase text-[8px] tracking-wider">Campaign</span>
                                <span className="text-slate-300 font-bold truncate block" title={recommendedTriage.threatIntel.campaign}>{recommendedTriage.threatIntel.campaign || 'N/A'}</span>
                              </div>
                              <div className="bg-slate-950/40 border border-slate-850 p-2 rounded-lg">
                                <span className="text-slate-500 block font-semibold uppercase text-[8px] tracking-wider">Malware Family</span>
                                <span className="text-slate-300 font-bold">{recommendedTriage.threatIntel.malwareFamily || 'N/A'}</span>
                              </div>
                              <div className="bg-slate-950/40 border border-slate-850 p-2 rounded-lg">
                                <span className="text-slate-500 block font-semibold uppercase text-[8px] tracking-wider">Matched Indicator</span>
                                <span className="text-rose-400 font-mono font-bold truncate block" title={recommendedTriage.threatIntel.matchedIndicator}>{recommendedTriage.threatIntel.matchedIndicator || 'N/A'}</span>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Similar Historical Incidents Row */}
                        {recommendedTriage.similarIncidents && recommendedTriage.similarIncidents.length > 0 && (
                          <div className="space-y-2">
                            <div className="flex items-center gap-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                              <History className="w-3.5 h-3.5 text-blue-400" />
                              <span>Similar Historical Cases</span>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                              {recommendedTriage.similarIncidents.map((hist: any) => (
                                <div key={hist.id} className="bg-slate-900/40 border border-slate-800 rounded-lg p-3 flex flex-col justify-between space-y-2">
                                  <div>
                                    <div className="flex justify-between items-center">
                                      <span className="text-[10px] font-bold text-slate-300 truncate pr-2 max-w-[180px]">
                                        #{hist.id} • {hist.title}
                                      </span>
                                      <span className={`text-[8px] font-extrabold px-1.5 py-0.5 rounded uppercase tracking-wider ${
                                        hist.verdict === 'TRUE_POSITIVE' 
                                          ? 'bg-red-950/30 text-red-400 border border-red-900/20' 
                                          : hist.verdict === 'FALSE_POSITIVE' 
                                          ? 'bg-emerald-950/30 text-emerald-400 border border-emerald-900/20' 
                                          : 'bg-slate-800 text-slate-400'
                                      }`}>
                                        {hist.verdict}
                                      </span>
                                    </div>
                                    <p className="text-[10.5px] text-slate-400 mt-1 leading-relaxed">
                                      {hist.similarityReason}
                                    </p>
                                  </div>
                                  <div className="text-[8px] text-slate-500 font-mono text-right">
                                    Resolved: {hist.resolvedAt ? new Date(hist.resolvedAt).toLocaleDateString() : 'Active/Unresolved'}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Playbook Recommendations */}
                        {recommendedTriage.recommendedPlaybooks && recommendedTriage.recommendedPlaybooks.length > 0 && (
                          <div className="space-y-3">
                            <div className="flex items-center gap-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                              <Shield className="w-3.5 h-3.5 text-emerald-400" />
                              <span>Actionable Containment Playbooks</span>
                            </div>
                            
                            <div className="space-y-4">
                              {recommendedTriage.recommendedPlaybooks.map((playbook: any) => {
                                return (
                                  <div key={playbook.id} className="bg-slate-900/30 border border-slate-800/80 rounded-xl p-4 space-y-3">
                                    <div className="flex justify-between items-start flex-wrap gap-2">
                                      <div>
                                        <h5 className="text-[11.5px] font-bold text-slate-200">{playbook.name}</h5>
                                        <p className="text-[10px] text-slate-400 mt-0.5">{playbook.description}</p>
                                      </div>
                                      <div className="flex gap-1.5 flex-shrink-0">
                                        <span className="text-[8px] bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded font-mono font-bold uppercase">
                                          {playbook.duration}
                                        </span>
                                        <span className={`text-[8px] px-1.5 py-0.5 rounded font-bold uppercase ${
                                          playbook.difficulty === 'Low'
                                            ? 'bg-emerald-950/40 text-emerald-400'
                                            : playbook.difficulty === 'Medium'
                                            ? 'bg-amber-950/40 text-amber-400'
                                            : 'bg-rose-950/40 text-rose-400'
                                        }`}>
                                          {playbook.difficulty} Difficulty
                                        </span>
                                      </div>
                                    </div>

                                    {/* Playbook Match Reason */}
                                    <div className="bg-slate-950/30 border-l-2 border-emerald-500/40 px-3 py-1.5 rounded-r-lg">
                                      <p className="text-[9.5px] text-slate-400 italic">
                                        <span className="font-semibold text-emerald-400">Triage rationale:</span> {playbook.matchReason}
                                      </p>
                                    </div>

                                    {/* Action items with checklist */}
                                    <div className="space-y-1.5">
                                      <p className="text-[9px] text-slate-500 font-bold uppercase tracking-wider">Playbook Checklist</p>
                                      <div className="space-y-1">
                                        {playbook.recommendedActions?.map((action: string, stepIdx: number) => {
                                          const stepKey = `${playbook.id}-${stepIdx}`;
                                          const isChecked = completedTriageSteps.includes(stepKey);
                                          return (
                                            <button
                                              key={stepIdx}
                                              type="button"
                                              onClick={() => {
                                                if (isChecked) {
                                                  setCompletedTriageSteps(completedTriageSteps.filter(k => k !== stepKey));
                                                } else {
                                                  setCompletedTriageSteps([...completedTriageSteps, stepKey]);
                                                }
                                              }}
                                              className="w-full text-left bg-slate-950/40 hover:bg-slate-950 border border-slate-850 hover:border-slate-800 rounded-lg px-3 py-2 flex items-center gap-2.5 transition-all text-[10.5px] cursor-pointer group"
                                            >
                                              <div className={`w-3.5 h-3.5 rounded flex items-center justify-center transition-all ${
                                                isChecked 
                                                  ? 'bg-emerald-500 text-slate-950' 
                                                  : 'border border-slate-700 group-hover:border-slate-500'
                                              }`}>
                                                {isChecked && <Check className="w-2.5 h-2.5 stroke-[4]" />}
                                              </div>
                                              <span className={`transition-all ${isChecked ? 'text-slate-500 line-through' : 'text-slate-300'}`}>
                                                {action}
                                              </span>
                                            </button>
                                          );
                                        })}
                                      </div>
                                    </div>

                                    {/* Execute Button */}
                                    <div className="flex justify-end pt-1">
                                      <button
                                        type="button"
                                        onClick={() => triggerSOAR(playbook.id)}
                                        disabled={actionLoading !== null}
                                        className="bg-slate-850 hover:bg-slate-800 text-slate-200 border border-slate-700 hover:border-slate-600 px-3 py-1 rounded-md text-[10px] font-bold flex items-center gap-1.5 transition-all cursor-pointer shadow-sm hover:shadow-md"
                                      >
                                        {actionLoading === playbook.id ? (
                                          <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-400" />
                                        ) : (
                                          <Zap className="w-3.5 h-3.5 text-emerald-400" />
                                        )}
                                        {actionLoading === playbook.id ? 'Running Playbook...' : 'Trigger Automated Action'}
                                      </button>
                                    </div>

                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                      </div>
                    ) : (
                      <p className="text-[10px] text-slate-500 italic">No triage recommendations available.</p>
                    )}
                  </div>

                  {/* Related Alerts */}
                  {incidentDetails?.alerts && incidentDetails.alerts.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-500" /> Correlated Alerts ({incidentDetails.alerts.length})
                      </h4>
                      <div className="space-y-2">
                        {incidentDetails.alerts.slice(0, 5).map((alert: any) => (
                          <div key={alert.id} className="bg-slate-950/40 border border-slate-800 rounded-lg p-3 flex justify-between items-center">
                            <div>
                              <span className="text-[10px] font-semibold text-slate-200">{alert.title}</span>
                              <p className="text-[9px] text-slate-500 mt-0.5">
                                {alert.attack_type} • IP:{' '}
                                <button
                                  type="button"
                                  onClick={() => {
                                    setBlockingIp(alert.attacker_ip);
                                    setBlockReason(`Incident correlation: ${alert.title} (${alert.attack_type})`);
                                  }}
                                  className="font-mono text-rose-400 hover:text-rose-300 hover:underline bg-rose-950/20 hover:bg-rose-950/40 px-1 py-0.5 rounded border border-rose-900/30 hover:border-rose-700/50 font-semibold cursor-pointer transition-all inline-flex items-center gap-1"
                                  title="Click for Quick Block"
                                >
                                  {alert.attacker_ip}
                                </button>
                              </p>
                            </div>
                            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                              alert.severity === 'CRITICAL' ? 'bg-red-950/40 text-red-400' : 'bg-amber-950/40 text-amber-400'
                            }`}>{alert.severity}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Analyst Notes */}
                  <div className="space-y-2">
                    <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider">Analyst Notes</label>
                    <textarea
                      value={notes}
                      onChange={e => setNotes(e.target.value)}
                      className="w-full bg-slate-950/60 border border-slate-800 rounded-xl px-4 py-3 text-xs focus:outline-none focus:border-blue-500/50 transition-all text-slate-200 h-24 resize-none"
                      placeholder="Enter investigation observations, hypothesis, or findings..."
                    />
                  </div>
                </>
              )}

              {/* INVESTIGATION TAB */}
              {activeTab === 'investigation' && (
                <div className="space-y-4">
                  {investigationLoading ? (
                    <div className="flex flex-col items-center justify-center py-16 gap-3">
                      <Loader2 className="w-8 h-8 text-indigo-400 animate-spin" />
                      <p className="text-xs text-slate-400">Running multi-agent investigation pipeline...</p>
                      <p className="text-[10px] text-slate-600">Planner → Supervisor → Threat Hunter → SOAR → Executive</p>
                    </div>
                  ) : investigation ? (
                    <div className="space-y-3">
                      <div className="bg-indigo-950/20 border border-indigo-800/30 rounded-xl p-4">
                        <h4 className="text-xs font-bold text-indigo-300 mb-2">Agent Team Results</h4>
                        {investigation.messages?.map((msg: string, idx: number) => (
                          <div key={idx} className="text-[11px] text-slate-300 py-1.5 border-b border-slate-800/50 last:border-0 flex items-start gap-2">
                            <ChevronRight className="w-3 h-3 text-indigo-400 mt-0.5 flex-shrink-0" />
                            <span>{msg}</span>
                          </div>
                        ))}
                      </div>

                      {/* XAI Panel Integration */}
                      {investigation.xai_payload && (
                        <div className="mt-4">
                          <XAIPanel xaiData={investigation.xai_payload} />
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-16 text-slate-500 gap-3">
                      <Brain className="w-10 h-10 opacity-30" />
                      <p className="text-xs">Click "Investigate" to run the multi-agent pipeline</p>
                    </div>
                  )}
                </div>
              )}

              {/* TIMELINE TAB */}
              {activeTab === 'timeline' && (
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                  
                  {/* Left Column: State Transitions Timeline */}
                  <div className="space-y-4">
                    <div className="flex items-center gap-2">
                      <Activity className="w-4 h-4 text-blue-400" />
                      <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">State Transition Lifecycle</h4>
                    </div>
                    
                    <div className="relative pl-8 border-l border-slate-800 space-y-6">
                      {getStateTransitions(selectedIncident).map((step, idx) => {
                        const StepIcon = step.icon;
                        const isCompleted = step.status === 'completed';
                        const isActive = step.status === 'active';
                        
                        return (
                          <div key={idx} className="relative">
                            
                            {/* Timeline Point Indicator */}
                            <div className="absolute -left-[45px] top-0.5 flex items-center justify-center">
                              <div className={`w-8 h-8 rounded-full flex items-center justify-center border transition-all ${
                                isCompleted 
                                  ? 'bg-slate-900 border-emerald-500/50 text-emerald-400' 
                                  : isActive 
                                  ? 'bg-slate-900 border-blue-500 text-blue-400 animate-pulse' 
                                  : 'bg-slate-950 border-slate-800 text-slate-600'
                              }`}>
                                <StepIcon className="w-4 h-4" />
                              </div>
                              
                              {/* Glowing state indicator inside dot */}
                              <div className={`absolute w-2 h-2 rounded-full ${step.dotColor}`} style={{ top: '12px', left: '12px' }} />
                            </div>

                            {/* Transition content card */}
                            <div className={`border rounded-xl p-4 transition-all space-y-2 ${
                              isCompleted 
                                ? 'bg-slate-900/40 border-slate-800/80' 
                                : isActive 
                                ? 'bg-blue-950/10 border-blue-900/30 shadow-[0_0_12px_rgba(59,130,246,0.05)]' 
                                : 'bg-slate-950/10 border-slate-900/60 opacity-60'
                            }`}>
                              <div className="flex justify-between items-start flex-wrap gap-2">
                                <div>
                                  <span className={`text-[9px] uppercase tracking-wider font-extrabold px-1.5 py-0.5 rounded ${
                                    isCompleted 
                                      ? 'bg-emerald-950/50 text-emerald-400 border border-emerald-900/20' 
                                      : isActive 
                                      ? 'bg-blue-950/50 text-blue-400 border border-blue-900/20' 
                                      : 'bg-slate-900 text-slate-500 border border-slate-800/50'
                                  }`}>
                                    {step.phase}
                                  </span>
                                  <h5 className="text-[11.5px] font-bold text-slate-200 mt-1.5">{step.title}</h5>
                                </div>
                                <span className="text-[9px] text-slate-500 font-mono font-semibold">{step.timestamp}</span>
                              </div>

                              <p className="text-[10.5px] text-slate-400 leading-relaxed">
                                {step.description}
                              </p>

                              {/* Nested Details List */}
                              {step.details && step.details.length > 0 && (
                                <div className="pt-2 border-t border-slate-850/60 space-y-1">
                                  {step.details.map((detail, dIdx) => (
                                    <div key={dIdx} className="text-[10px] text-slate-500 flex items-start gap-1.5">
                                      <ChevronRight className="w-3 h-3 text-slate-600 mt-0.5 flex-shrink-0" />
                                      <span className="leading-normal">{detail}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>

                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Right Column: Related Logs Event Timeline */}
                  <div className="space-y-4 border-t xl:border-t-0 xl:border-l border-slate-800 xl:pl-6 pt-6 xl:pt-0">
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4 text-slate-400" />
                      <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">Raw Ingested Security Events</h4>
                    </div>
                    
                    {incidentDetails?.related_logs && incidentDetails.related_logs.length > 0 ? (
                      <div className="relative pl-6 border-l border-slate-800 space-y-4">
                        {incidentDetails.related_logs.slice(0, 20).map((log: any, idx: number) => (
                          <div key={idx} className="relative">
                            <div className="absolute -left-[29px] top-1.5 w-2 h-2 rounded-full bg-slate-800 border border-blue-500 shadow-[0_0_4px_rgba(59,130,246,0.5)]"></div>
                            <div className="bg-slate-950/40 border border-slate-850 rounded-lg p-3 space-y-1">
                              <div className="flex justify-between items-center">
                                <span className="text-[10px] font-bold text-slate-300 font-mono tracking-wide">{log.event_type || 'Log Event'}</span>
                                <span className="text-[9px] text-slate-500 font-mono">{new Date(log.timestamp).toLocaleString()}</span>
                              </div>
                              <p className="text-[10px] text-slate-400">
                                IP: <span className="font-mono text-slate-300 bg-slate-900 px-1 py-0.5 rounded">{log.source_ip}</span>
                                {log.endpoint && <> • Endpoint: <span className="font-mono text-slate-300 bg-slate-900 px-1 py-0.5 rounded">{log.endpoint}</span></>}
                                {log.user_id && <> • User: <span className="text-slate-300 bg-slate-900 px-1 py-0.5 rounded">{log.user_id}</span></>}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center py-16 text-slate-500 text-xs gap-2 bg-slate-950/20 border border-slate-850 rounded-xl">
                        <Clock className="w-6 h-6 opacity-30" />
                        <span className="text-slate-500">No raw event telemetry available</span>
                      </div>
                    )}
                  </div>

                </div>
              )}

              {/* MITRE TAB */}
              {activeTab === 'mitre' && (
                <div className="space-y-4">
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                    <Target className="w-3.5 h-3.5 text-violet-400" /> MITRE ATT&CK Mapping
                  </h4>
                  {incidentDetails?.alerts?.map((alert: any) => {
                    const mitre = alert.mitre_mapping || {};
                    return (
                      <div key={alert.id} className="bg-slate-950/40 border border-slate-800 rounded-xl p-4 space-y-3">
                        <p className="text-xs font-semibold text-slate-200">Alert: {alert.attack_type}</p>
                        <div className="grid grid-cols-2 gap-2">
                          {mitre.techniques?.map((tech: any, idx: number) => (
                            <div key={idx} className="bg-violet-950/20 border border-violet-800/30 rounded-lg p-2.5">
                              <p className="text-[10px] font-bold text-violet-300">{tech.technique_id}</p>
                              <p className="text-[9px] text-slate-400">{tech.technique_name}</p>
                            </div>
                          )) || (
                            <p className="text-[10px] text-slate-500 col-span-2">MITRE mapping will populate after investigation</p>
                          )}
                        </div>
                      </div>
                    );
                  }) || (
                    <div className="flex items-center justify-center py-12 text-slate-500 text-xs gap-2">
                      <Target className="w-5 h-5 opacity-30" /> Run investigation to generate MITRE mappings
                    </div>
                  )}
                </div>
              )}

              {/* SOAR TAB */}
              {activeTab === 'soar' && (
                <div className="space-y-5">
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                    <Zap className="w-4 h-4 text-blue-500" /> Containment Playbooks
                  </h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {[
                      { action: 'IP_BLOCK', label: 'Block Source IP', icon: Lock, hoverColor: 'hover:border-red-800/40 hover:bg-red-950/10' },
                      { action: 'HOST_ISOLATE', label: 'Isolate Host', icon: Shield, hoverColor: 'hover:border-red-800/40 hover:bg-red-950/10' },
                      { action: 'USER_DISABLE', label: 'Disable User', icon: UserX, hoverColor: 'hover:border-red-800/40 hover:bg-red-950/10' },
                      { action: 'JIRA_TICKET', label: 'Create Ticket', icon: FileSpreadsheet, hoverColor: 'hover:border-blue-800/40 hover:bg-blue-950/10' },
                    ].map(btn => {
                      const Icon = btn.icon;
                      return (
                        <button
                          key={btn.action}
                          onClick={() => triggerSOAR(btn.action)}
                          disabled={actionLoading !== null}
                          className={`bg-slate-950 border border-slate-800 ${btn.hoverColor} p-4 rounded-xl text-center group transition-all text-xs font-semibold`}
                        >
                          <Icon className="w-5 h-5 mx-auto mb-2 text-slate-400 group-hover:text-slate-200 transition-all" />
                          {actionLoading === btn.action ? 'Executing...' : btn.label}
                        </button>
                      );
                    })}
                  </div>

                  {/* Natural Language SOAR */}
                  <VoiceCommandBar />

                  {/* Execution Log */}
                  {soarLog.length > 0 && (
                    <div className="space-y-2">
                      <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider">Execution Feed</label>
                      <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 font-mono text-[10px] text-slate-300 space-y-1.5 h-40 overflow-y-auto">
                        {soarLog.map((log, idx) => (
                          <div key={idx} className="truncate">
                            <span className="text-blue-500">[{new Date().toLocaleTimeString()}]</span> {log}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-3">
            <div className="w-16 h-16 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center">
              <AlertTriangle className="w-8 h-8 opacity-30 text-blue-500" />
            </div>
            <span className="text-xs">Select an incident to begin triage workbench</span>
            <span className="text-[10px] text-slate-600">Use filters and search to narrow down incidents</span>
          </div>
        )}
      </div>

      <QuickBlockModal
        isOpen={blockingIp !== null}
        onClose={() => setBlockingIp(null)}
        ipAddress={blockingIp || ''}
        initialReason={blockReason}
      />
      </div>
    </div>
  );
}
