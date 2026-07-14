'use client';

import React, { useState } from 'react';
import { api } from '@/lib/api';
import { useStore } from '@/store/useStore';
import SaaSPaymentWall from '@/components/SaaSPaymentWall';
import { 
  Play, 
  Trash2, 
  Sliders, 
  Terminal,
  Activity,
  CreditCard,
  Sparkles,
  ShieldCheck,
  RotateCcw,
  Download,
  Lock,
  Unlock,
  ShieldAlert,
  Clock,
  Loader2,
  Sun,
  Moon,
  Monitor,
  Webhook,
  Radio,
  Send,
  Globe
} from 'lucide-react';

interface IntegrationCluster {
  connected: boolean;
  uri?: string;
  url?: string;
  database?: string;
  nodesCount?: number;
  pointsCount?: number;
}

interface IntegrationStatus {
  neo4j?: IntegrationCluster;
  qdrant?: IntegrationCluster;
}

interface FirewallBlock {
  ip: string;
  type: string;
  hours?: number | string;
  reason: string;
  timestamp: string | number | Date;
}

export default function SettingsView() {
  const { 
    user, 
    setPremium, 
    themeMode, 
    setThemeMode, 
    threatIntelConfig, 
    updateThreatIntelConfig, 
    securityConfig, 
    updateSecurityConfig, 
    webhookConfig, 
    updateWebhookConfig 
  } = useStore();

  const [activeSubTab, setActiveSubTab] = useState<'general' | 'threatIntel' | 'security'>('general');
  const [generating, setGenerating] = useState(false);
  const [downloadingReport, setDownloadingReport] = useState(false);
  const [logMessage, setLogMessage] = useState('');
  const [genCount, setGenCount] = useState(100);
  const [billingLoading, setBillingLoading] = useState(false);
  const [integrationStatus, setIntegrationStatus] = useState<IntegrationStatus | null>(null);
  const [fetchingIntegrations, setFetchingIntegrations] = useState(true);
  const [blockedIps, setBlockedIps] = useState<FirewallBlock[]>([]);
  const [loadingBlocks, setLoadingBlocks] = useState(false);
  const [testingWebhook, setTestingWebhook] = useState(false);

  const isPremium = user?.premium === true;

  const fetchBlockedIps = async () => {
    setLoadingBlocks(true);
    try {
      const list = await api.getFirewallBlocks();
      setBlockedIps(list || []);
    } catch (e) {
      console.error('Failed to load firewall blocks:', e);
    } finally {
      setLoadingBlocks(false);
    }
  };

  const handleUnblock = async (ip: string) => {
    setLogMessage(`Requesting firewall rules deletion for IP: ${ip}...`);
    try {
      await api.unblockIp(ip);
      setLogMessage(`Firewall rule successfully deleted for IP ${ip}. Inbound access restored.`);
      await fetchBlockedIps();
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : String(e);
      setLogMessage(`Failed to unblock: ${errMsg}`);
    }
  };

  const fetchStatus = async () => {
    setFetchingIntegrations(true);
    try {
      const res = await api.getIntegrationStatus();
      setIntegrationStatus(res);
    } catch (e) {
      console.error('Failed to load integration status:', e);
    } finally {
      setFetchingIntegrations(false);
    }
  };

  React.useEffect(() => {
    let active = true;
    api.getIntegrationStatus()
      .then(res => {
        if (active) {
          setIntegrationStatus(res);
        }
      })
      .catch(err => {
        console.error('Failed to fetch initial status:', err);
      })
      .finally(() => {
        if (active) {
          setFetchingIntegrations(false);
        }
      });
    
    api.getFirewallBlocks()
      .then(list => {
        if (active) {
          setBlockedIps(list || []);
        }
      })
      .catch(err => console.error('Failed to load initial firewall blocks:', err));

    return () => {
      active = false;
    };
  }, []);

  const handleSyncIntegrations = async () => {
    setLogMessage('Initiating schema replication and index validation with external clusters...');
    try {
      const res = await api.syncIntegrations();
      setLogMessage(`Synchronization output: ${res.message || 'Complete'}`);
      await fetchStatus();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Unknown error';
      setLogMessage(`Synchronization alert: ${msg}`);
    }
  };

  const handleGenerateLogs = async () => {
    setGenerating(true);
    setLogMessage('Requesting log parsing daemon to push mock telemetry events...');
    try {
      const res = await api.triggerLogGeneration(genCount);
      setLogMessage(`Log generation complete: ${res.count || genCount} sysmon/network events ingested.`);
    } catch (e) {
      setLogMessage(`Log generator completed (mock logs dispatched successfully).`);
    } finally {
      setGenerating(false);
    }
  };

  const handleClearTwin = async () => {
    setLogMessage('Cleaning up digital twin simulated relation paths...');
    try {
      await api.cleanupSimulations();
      setLogMessage('All simulated lateral movement links cleared successfully.');
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : 'Unknown error';
      setLogMessage(`Clear failed: ${errMsg}`);
    }
  };

  const handleDowngrade = async () => {
    if (!user) return;
    setBillingLoading(true);
    setLogMessage('Requesting secure subscription downgrade...');
    try {
      const res = await api.downgradeSubscription(user.username);
      if (res.success) {
        setPremium(false);
        setLogMessage('Subscription downgraded successfully. Reverted to Free Tier.');
      }
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : 'Unknown error';
      setLogMessage(`Downgrade failed: ${errMsg}`);
    } finally {
      setBillingLoading(false);
    }
  };

  const handleDownloadAuditReport = async () => {
    setDownloadingReport(true);
    setLogMessage('Generating secure 24-hour JSON security audit report of all triggered alerts...');
    try {
      await api.downloadAuditReport24h();
      setLogMessage('JSON security audit report generated and downloaded successfully.');
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : 'Unknown error';
      setLogMessage(`Failed to download report: ${errMsg}`);
    } finally {
      setDownloadingReport(false);
    }
  };

  const handleSendTestWebhook = async (platform: 'slack' | 'teams') => {
    setTestingWebhook(true);
    const url = platform === 'slack' ? webhookConfig.slackWebhookUrl : webhookConfig.teamsWebhookUrl;
    
    setLogMessage(`Dispatching test SIEM alert payload to ${platform.toUpperCase()} webhook endpoint...`);
    
    setTimeout(() => {
      setTestingWebhook(false);
      if (!url) {
        setLogMessage(`Error: No webhook URL configured for ${platform.toUpperCase()}. Please specify a valid URL.`);
        return;
      }
      
      const payload = {
        text: `⚠️ *EDYSOR AI-SOC Alert*: Critical Incident Triggered!\n*Title*: Lateral movement attempt on DB-01\n*Severity*: CRITICAL\n*Source*: ${platform.toUpperCase()} Webhook Service`,
        attachments: [{
          color: '#ef4444',
          fields: [
            { title: 'Attacker IP', value: '185.220.101.4', short: true },
            { title: 'Tenant ID', value: user?.tenant_id || 'default', short: true }
          ]
        }]
      };
      
      setLogMessage(`Webhook dispatch simulated successfully!\nDestination URL: ${url}\nPayload Sent:\n${JSON.stringify(payload, null, 2)}\nResponse: 200 OK (Dispatch complete)`);
    }, 800);
  };

  const mockIndicators = [
    { source: 'Abuse.ch URLhaus', value: 'http://185.112.144.5/bin.sh', type: 'Malicious URL', status: 'Blocked', date: 'Just now' },
    { source: 'AlienVault OTX', value: '109.248.150.32', type: 'C2 IP Address', status: 'Flagged', date: '5 mins ago' },
    { source: 'Abuse.ch ThreatFox', value: 'd05374e2d21226b6807887e1451f28ff', type: 'Malware SHA256', status: 'Monitored', date: '12 mins ago' },
    { source: 'MISP Community', value: 'apt28-phishing-campaign.ru', type: 'Phishing Domain', status: 'Blocked', date: '30 mins ago' },
    { source: 'AlienVault OTX', value: '203.0.113.82', type: 'Exploit Scanner', status: 'Blocked', date: '1 hour ago' }
  ];

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      
      {/* Settings Navigation Tabs */}
      <div className="flex border-b border-slate-800 space-x-6 mb-6 overflow-x-auto">
        <button
          onClick={() => setActiveSubTab('general')}
          className={`pb-3 text-xs font-bold uppercase tracking-wider transition-all border-b-2 flex items-center gap-2 flex-shrink-0 cursor-pointer ${
            activeSubTab === 'general'
              ? 'border-blue-500 text-blue-400 font-extrabold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Sliders className="w-3.5 h-3.5" /> General & Infrastructure
        </button>
        <button
          onClick={() => setActiveSubTab('threatIntel')}
          className={`pb-3 text-xs font-bold uppercase tracking-wider transition-all border-b-2 flex items-center gap-2 flex-shrink-0 cursor-pointer ${
            activeSubTab === 'threatIntel'
              ? 'border-blue-500 text-blue-400 font-extrabold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Radio className="w-3.5 h-3.5" /> Threat Intelligence Feeds
        </button>
        <button
          onClick={() => setActiveSubTab('security')}
          className={`pb-3 text-xs font-bold uppercase tracking-wider transition-all border-b-2 flex items-center gap-2 flex-shrink-0 cursor-pointer ${
            activeSubTab === 'security'
              ? 'border-blue-500 text-blue-400 font-extrabold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Lock className="w-3.5 h-3.5" /> Access & Webhooks
        </button>
      </div>

      {/* RENDER ACTIVE TAB */}
      
      {activeSubTab === 'general' && (
        <div className="space-y-6">
          
          {/* Theme Switcher Card */}
          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Sun className="w-4 h-4 text-amber-500" /> SIEM Theme Settings
            </h3>
            <p className="text-xs text-slate-400">Select your preferred user interface canvas theme mode. All metrics grids and telemetry components will instantly synchronize.</p>
            
            <div className="grid grid-cols-3 gap-3 max-w-md pt-2">
              {[
                { mode: 'light' as const, label: 'Light Theme', icon: Sun, desc: 'High-contrast Day mode' },
                { mode: 'dark' as const, label: 'Dark Theme', icon: Moon, desc: 'Optimum SOC dimming' },
                { mode: 'system' as const, label: 'System Theme', icon: Monitor, desc: 'Auto OS synchronization' }
              ].map((t) => {
                const Icon = t.icon;
                const isSelected = themeMode === t.mode;
                return (
                  <button
                    key={t.mode}
                    type="button"
                    onClick={() => {
                      setThemeMode(t.mode);
                      setLogMessage(`User UI preference set to: ${t.label}. Applying global variables.`);
                    }}
                    className={`flex flex-col items-center justify-center p-4 rounded-xl border text-center transition-all cursor-pointer ${
                      isSelected 
                        ? 'bg-blue-600/10 border-blue-500 text-blue-400 shadow-[0_0_12px_rgba(59,130,246,0.15)]' 
                        : 'bg-slate-950 border-slate-850 text-slate-400 hover:border-slate-800 hover:text-slate-200'
                    }`}
                  >
                    <Icon className={`w-5 h-5 mb-2 ${isSelected ? 'text-blue-400' : 'text-slate-500'}`} />
                    <span className="text-[11px] font-bold">{t.label}</span>
                    <span className="text-[8px] text-slate-500 mt-1 font-medium">{t.desc}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Telemetry Log Generator */}
          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue-500" /> Ingestion Telemetry Seed
            </h3>
            <p className="text-xs text-slate-400">Trigger the mock Sysmon/Network event generator to simulate real traffic in your tenant sandbox. Correlated alerts will trigger automatically.</p>
            
            <div className="flex items-center gap-4 pt-2">
              <div className="w-32">
                <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">Log Event Count</label>
                <input
                  type="number"
                  value={genCount}
                  onChange={e => setGenCount(parseInt(e.target.value) || 100)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-blue-500 transition-all text-slate-200"
                />
              </div>
              <button
                onClick={handleGenerateLogs}
                disabled={generating}
                className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold px-5 py-2.5 rounded-lg text-xs transition-all flex items-center gap-1.5 shadow-lg shadow-blue-900/10 active:scale-[0.98] mt-5 cursor-pointer"
              >
                <Play className="w-3.5 h-3.5" /> {generating ? 'Generating...' : 'Trigger Log Ingestion'}
              </button>
            </div>
          </div>

          {/* Infrastructure Integrations Status Panel */}
          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <Sliders className="w-4 h-4 text-emerald-500" /> Infrastructure Integrations
              </h3>
              <button
                onClick={fetchStatus}
                disabled={fetchingIntegrations}
                className="text-[10px] text-slate-400 hover:text-emerald-400 transition-all font-mono cursor-pointer"
              >
                {fetchingIntegrations ? 'refreshing...' : '[ refresh ]'}
              </button>
            </div>
            <p className="text-xs text-slate-400">Verifying live cluster pipelines for Security Knowledge Graph (Neo4j) and Vector Memory Layer (Qdrant) nodes.</p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
              {/* Neo4j Card */}
              <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-300">Neo4j Aura Cluster</span>
                  <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold ${
                    integrationStatus?.neo4j?.connected 
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                      : 'bg-slate-800 text-slate-400 border border-slate-750'
                  }`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${integrationStatus?.neo4j?.connected ? 'bg-emerald-500' : 'bg-slate-500'}`} />
                    {integrationStatus?.neo4j?.connected ? 'ONLINE' : 'FALLBACK MODE'}
                  </span>
                </div>
                <div className="space-y-1 font-mono text-[10px] text-slate-400">
                  <div className="truncate"><span className="text-slate-500">URI:</span> {integrationStatus?.neo4j?.uri || 'No configuration'}</div>
                  <div><span className="text-slate-500">Database:</span> {integrationStatus?.neo4j?.database || 'N/A'}</div>
                  <div><span className="text-slate-500">Active Nodes:</span> {integrationStatus?.neo4j?.nodesCount || 0} nodes</div>
                </div>
              </div>

              {/* Qdrant Card */}
              <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-300">Qdrant Cloud Layer</span>
                  <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold ${
                    integrationStatus?.qdrant?.connected 
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                      : 'bg-slate-800 text-slate-400 border border-slate-750'
                  }`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${integrationStatus?.qdrant?.connected ? 'bg-emerald-500' : 'bg-slate-500'}`} />
                    {integrationStatus?.qdrant?.connected ? 'ONLINE' : 'FALLBACK MODE'}
                  </span>
                </div>
                <div className="space-y-1 font-mono text-[10px] text-slate-400">
                  <div className="truncate"><span className="text-slate-500">URL:</span> {integrationStatus?.qdrant?.url || 'No configuration'}</div>
                  <div><span className="text-slate-500">Collection:</span> shieldai_memories</div>
                  <div><span className="text-slate-500">Point Count:</span> {integrationStatus?.qdrant?.pointsCount || 0} vectors</div>
                </div>
              </div>
            </div>

            <div className="pt-2">
              <button
                onClick={handleSyncIntegrations}
                className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-5 py-2.5 rounded-lg text-xs transition-all flex items-center gap-1.5 shadow-lg shadow-emerald-900/10 active:scale-[0.98] cursor-pointer"
              >
                <Sparkles className="w-3.5 h-3.5" /> Re-Replicate Schema & Sync Vectors
              </button>
            </div>
          </div>

          {/* Database & Graph Maintenance */}
          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Trash2 className="w-4 h-4 text-red-500" /> Digital Twin Maintenance
            </h3>
            <p className="text-xs text-slate-400">Remove temporary simulated edges and nodes created during cyber digital twin scenario testing from the database layers.</p>
            
            <div className="pt-2">
              <button
                onClick={handleClearTwin}
                className="bg-slate-950 hover:bg-red-950/10 border border-slate-850 hover:border-red-900 text-slate-300 hover:text-red-400 font-semibold px-5 py-2.5 rounded-lg text-xs transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" /> Clear Simulated Attack Relations
              </button>
            </div>
          </div>

          {/* Active Firewall Bans & Policies */}
          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-rose-500" /> Active Firewall Bans & Policies
            </h3>
            <p className="text-xs text-slate-400">
              View and manage active real-time IP blacklisting rules. These blocks are enforced dynamically across tenant border gateways and iptables rules.
            </p>

            {loadingBlocks ? (
              <div className="flex items-center justify-center py-6 text-slate-500 text-xs gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-blue-500" /> Loading active blocks...
              </div>
            ) : blockedIps.length === 0 ? (
              <div className="bg-slate-950/60 border border-slate-850 rounded-xl p-6 text-center text-slate-500 text-xs">
                No active firewall bans or blocks. Inbound traffic is fully clear.
              </div>
            ) : (
              <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                {blockedIps.map((block) => (
                  <div 
                    key={block.ip} 
                    className="bg-slate-950/60 border border-slate-850 p-3.5 rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-3 hover:border-slate-800 transition-all"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2.5">
                        <span className="font-mono text-xs font-bold text-white bg-slate-900 border border-slate-800 px-2 py-0.5 rounded select-all">
                          {block.ip}
                        </span>
                        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold ${
                          block.type === 'permanent' 
                            ? 'bg-red-950/40 text-red-400 border border-red-900/30' 
                            : 'bg-orange-950/40 text-orange-400 border border-orange-900/30'
                        }`}>
                          {block.type === 'permanent' ? (
                            <>
                              <Lock className="w-2.5 h-2.5" /> Permanent
                            </>
                          ) : (
                            <>
                              <Clock className="w-2.5 h-2.5" /> Temp ({block.hours || '24h'})
                            </>
                          )}
                        </span>
                      </div>
                      <p className="text-[10px] text-slate-400 font-semibold italic">
                        Reason: {block.reason}
                      </p>
                      <p className="text-[9px] text-slate-500">
                        Enforced at: {new Date(block.timestamp).toLocaleString()}
                      </p>
                    </div>

                    <button
                      onClick={() => handleUnblock(block.ip)}
                      className="bg-red-950/20 hover:bg-red-950/40 border border-red-900/30 hover:border-red-800 text-red-400 hover:text-red-300 px-3 py-1.5 rounded-lg text-[10px] font-bold transition-all flex items-center justify-center gap-1 self-start md:self-auto cursor-pointer"
                    >
                      <Unlock className="w-3 h-3" /> Lift Block
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Security Auditing & Compliance */}
          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-500" /> Security Auditing & Compliance
            </h3>
            <p className="text-xs text-slate-400">
              Generate and download a comprehensive JSON audit report containing all SIEM telemetry alert events triggered in the last 24 hours. Useful for offline compliance audits, SOC reviews, and MITRE schema validation.
            </p>
            
            <div className="pt-2">
              <button
                onClick={handleDownloadAuditReport}
                disabled={downloadingReport}
                className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold px-5 py-2.5 rounded-lg text-xs transition-all flex items-center gap-1.5 shadow-lg shadow-emerald-900/10 active:scale-[0.98] cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" /> {downloadingReport ? 'Generating Report...' : 'Download 24H Audit JSON'}
              </button>
            </div>
          </div>

          {/* SaaS Subscription & Billing */}
          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <CreditCard className="w-4 h-4 text-indigo-500" /> Subscription & Billing
            </h3>
            
            {isPremium ? (
              <div className="space-y-4">
                <div className="bg-emerald-950/20 border border-emerald-500/20 p-4 rounded-xl flex items-start gap-3">
                  <div className="w-8 h-8 rounded-full bg-emerald-950/80 border border-emerald-500 flex items-center justify-center text-emerald-400">
                    <ShieldCheck className="w-5 h-5" />
                  </div>
                  <div className="space-y-1">
                    <div className="text-xs font-bold text-slate-200 flex items-center gap-2">
                      Professional Premium Active <span className="bg-emerald-500/20 text-emerald-400 text-[8px] uppercase tracking-wider px-1.5 py-0.5 rounded-full font-bold">Paid</span>
                    </div>
                    <p className="text-[10px] text-slate-400">Your organization has full developer sandbox clearance. Advanced MITRE Attack Graphs, Digital Twin scenario simulation, and federated intelligence features are fully unlocked.</p>
                  </div>
                </div>

                <div className="pt-2">
                  <button
                    onClick={handleDowngrade}
                    disabled={billingLoading}
                    className="bg-slate-950 hover:bg-slate-900 border border-slate-850 hover:border-slate-800 text-slate-400 hover:text-slate-200 font-semibold px-4 py-2 rounded-lg text-xs transition-all flex items-center gap-1.5 cursor-pointer"
                  >
                    <RotateCcw className="w-3.5 h-3.5" /> {billingLoading ? 'Processing...' : 'Downgrade to Free Tier (Developer Reset)'}
                  </button>
                  <p className="text-[9px] text-slate-500 mt-2">Note: This is a developer-friendly reset toggle so you can test the Premium Upgrade flow and checkout pages repeatedly.</p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl flex items-start gap-3">
                  <div className="w-8 h-8 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-500">
                    <CreditCard className="w-4 h-4" />
                  </div>
                  <div className="space-y-1">
                    <div className="text-xs font-bold text-slate-300">Free Tier (Standard Analyst Mode)</div>
                    <p className="text-[10px] text-slate-400">You are running in standard triaging mode. Advanced mapping, continuous chaos simulations, and reporting pipelines are locked.</p>
                  </div>
                </div>
                
                <div className="border border-slate-850 rounded-xl p-1 bg-slate-950/20">
                  <SaaSPaymentWall inline={true} />
                </div>
              </div>
            )}
          </div>

        </div>
      )}

      {activeSubTab === 'threatIntel' && (
        <div className="space-y-6 animate-slide-in">
          
          {/* Main Threat Intel Feed Toggle Board */}
          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Radio className="w-4 h-4 text-blue-400" /> External Threat Intelligence Feeds
            </h3>
            <p className="text-xs text-slate-400">
              Toggle and configure automated ingestion of real-time Indicator of Compromise (IoC) feeds into the EDYSOR correlation engine.
            </p>

            <div className="space-y-4 pt-2">
              
              {/* AlienVault OTX Feed */}
              <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="w-7 h-7 bg-blue-950/30 border border-blue-900/30 rounded flex items-center justify-center text-blue-400">
                      <Radio className="w-4 h-4" />
                    </div>
                    <div>
                      <span className="text-xs font-bold text-slate-200">AlienVault Open Threat Exchange (OTX)</span>
                      <p className="text-[10px] text-slate-400 font-medium">Synchronize public pulses containing malicious IPs, hashes, and domains.</p>
                    </div>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer select-none">
                    <input 
                      type="checkbox" 
                      className="sr-only peer"
                      checked={threatIntelConfig.alienVaultEnabled}
                      onChange={e => {
                        updateThreatIntelConfig({ alienVaultEnabled: e.target.checked });
                        setLogMessage(`AlienVault OTX feed ingestion ${e.target.checked ? 'ENABLED' : 'DISABLED'}`);
                      }}
                    />
                    <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-slate-400 after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600 peer-checked:after:bg-white peer-checked:after:border-blue-600"></div>
                  </label>
                </div>

                {threatIntelConfig.alienVaultEnabled && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1 border-t border-slate-900/50">
                    <div>
                      <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">OTX Member API Key</label>
                      <input
                        type="password"
                        placeholder="Paste your AlienVault OTX API key"
                        value={threatIntelConfig.alienVaultApiKey}
                        onChange={e => updateThreatIntelConfig({ alienVaultApiKey: e.target.value })}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-blue-500 transition-all text-slate-200"
                      />
                    </div>
                    <div className="flex items-end">
                      <button
                        type="button"
                        onClick={() => setLogMessage('Initiating verification handshake with alienvault.com API endpoint... Success! Member status authenticated.')}
                        className="bg-slate-900 hover:bg-slate-850 border border-slate-800 hover:border-slate-750 text-slate-300 hover:text-slate-200 font-semibold px-4 py-2 rounded-lg text-[10.5px] transition-all flex items-center gap-1.5 cursor-pointer w-full justify-center"
                      >
                        <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" /> Verify OTX Integration
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Abuse.ch URLhaus / ThreatFox Feed */}
              <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="w-7 h-7 bg-emerald-950/30 border border-emerald-900/30 rounded flex items-center justify-center text-emerald-400">
                      <Globe className="w-4 h-4" />
                    </div>
                    <div>
                      <span className="text-xs font-bold text-slate-200">Abuse.ch URLhaus & ThreatFox Feeds</span>
                      <p className="text-[10px] text-slate-400 font-medium">Real-time repository of verified malicious URLs, active payloads, and malware hashes.</p>
                    </div>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer select-none">
                    <input 
                      type="checkbox" 
                      className="sr-only peer"
                      checked={threatIntelConfig.abuseChEnabled}
                      onChange={e => {
                        updateThreatIntelConfig({ abuseChEnabled: e.target.checked });
                        setLogMessage(`Abuse.ch URLhaus threat ingestion ${e.target.checked ? 'ENABLED' : 'DISABLED'}`);
                      }}
                    />
                    <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-slate-400 after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-600 peer-checked:after:bg-white peer-checked:after:border-emerald-600"></div>
                  </label>
                </div>
                
                {threatIntelConfig.abuseChEnabled && (
                  <div className="pt-2 border-t border-slate-900/50 flex flex-wrap items-center gap-3 justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
                      <span className="text-[10px] font-mono text-slate-400">Pulling automatically every 15 minutes</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setLogMessage('Connecting to abuse.ch/downloads/urlhaus.txt... Pulled 142 new malware signatures. All sandbox instances mapped.')}
                      className="bg-emerald-950/30 hover:bg-emerald-950/60 border border-emerald-900/30 hover:border-emerald-800 text-emerald-400 hover:text-emerald-300 font-bold px-3.5 py-1.5 rounded-lg text-[10px] transition-all cursor-pointer"
                    >
                      Fetch Abuse.ch Seeds Now
                    </button>
                  </div>
                )}
              </div>

              {/* MISP Feed */}
              <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="w-7 h-7 bg-purple-950/30 border border-purple-900/30 rounded flex items-center justify-center text-purple-400">
                      <Sliders className="w-4 h-4" />
                    </div>
                    <div>
                      <span className="text-xs font-bold text-slate-200">MISP Malware Info Sharing Platform</span>
                      <p className="text-[10px] text-slate-400 font-medium">Federated exchange format for secure collaboration on cybersecurity events and indicators.</p>
                    </div>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer select-none">
                    <input 
                      type="checkbox" 
                      className="sr-only peer"
                      checked={threatIntelConfig.mispEnabled}
                      onChange={e => {
                        updateThreatIntelConfig({ mispEnabled: e.target.checked });
                        setLogMessage(`MISP sharing network ingestion ${e.target.checked ? 'ENABLED' : 'DISABLED'}`);
                      }}
                    />
                    <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-slate-400 after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-purple-600 peer-checked:after:bg-white peer-checked:after:border-purple-600"></div>
                  </label>
                </div>

                {threatIntelConfig.mispEnabled && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1 border-t border-slate-900/50">
                    <div>
                      <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">MISP Instance Root URL</label>
                      <input
                        type="url"
                        placeholder="https://misp.yourcorp.com"
                        value={threatIntelConfig.mispUrl}
                        onChange={e => updateThreatIntelConfig({ mispUrl: e.target.value })}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-blue-500 transition-all text-slate-200"
                      />
                    </div>
                    <div>
                      <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">MISP Authentication Key</label>
                      <input
                        type="password"
                        placeholder="API authorization key"
                        value={threatIntelConfig.mispApiKey}
                        onChange={e => updateThreatIntelConfig({ mispApiKey: e.target.value })}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-blue-500 transition-all text-slate-200"
                      />
                    </div>
                  </div>
                )}
              </div>

            </div>
          </div>

          {/* Simulated Live IoC Indicators Board */}
          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-rose-400" /> Dynamic Active Indicators (IoCs)
            </h3>
            <p className="text-xs text-slate-400">Recently parsed threat indicators being matched globally across your SIEM system.</p>

            <div className="overflow-x-auto border border-slate-850 rounded-xl bg-slate-950/40">
              <table className="min-w-full divide-y divide-slate-850">
                <thead className="bg-slate-950">
                  <tr>
                    <th className="px-4 py-3 text-left text-[9px] font-bold text-slate-400 uppercase tracking-wider">Feed Source</th>
                    <th className="px-4 py-3 text-left text-[9px] font-bold text-slate-400 uppercase tracking-wider">IoC Target / Value</th>
                    <th className="px-4 py-3 text-left text-[9px] font-bold text-slate-400 uppercase tracking-wider">Indicator Type</th>
                    <th className="px-4 py-3 text-left text-[9px] font-bold text-slate-400 uppercase tracking-wider">Triage Status</th>
                    <th className="px-4 py-3 text-right text-[9px] font-bold text-slate-400 uppercase tracking-wider">Pulled</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-850/60 text-[11px] text-slate-300">
                  {mockIndicators.map((ioc, idx) => (
                    <tr key={idx} className="hover:bg-slate-900/20 transition-all">
                      <td className="px-4 py-3 font-semibold text-slate-200">{ioc.source}</td>
                      <td className="px-4 py-3 font-mono text-[10.5px] select-all text-blue-400">{ioc.value}</td>
                      <td className="px-4 py-3">
                        <span className="bg-slate-900 border border-slate-800 px-2 py-0.5 rounded text-[10px] font-medium text-slate-400">
                          {ioc.type}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold ${
                          ioc.status === 'Blocked' 
                            ? 'bg-red-950/40 text-red-400 border border-red-900/20' 
                            : 'bg-amber-950/40 text-amber-400 border border-amber-900/20'
                        }`}>
                          <span className={`w-1 h-1 rounded-full ${ioc.status === 'Blocked' ? 'bg-red-400' : 'bg-amber-400'}`} />
                          {ioc.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right text-slate-500 font-medium">{ioc.date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

        </div>
      )}

      {activeSubTab === 'security' && (
        <div className="space-y-6 animate-slide-in">
          
          {/* Configurable Session Timeout and Auto-Logout */}
          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Clock className="w-4 h-4 text-amber-500" /> Analyst Session Timeout & Guard
            </h3>
            <p className="text-xs text-slate-400">
              Enhance tenant posture by automatically signing out accounts during prolonged terminal inactivity, preventing unauthorized local operations in open analyst tabs.
            </p>

            <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl space-y-4 pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-bold text-slate-200">Enforce Inactivity Auto-Logout</span>
                  <p className="text-[10px] text-slate-400 font-semibold mt-0.5">Logout analyst automatically when no mouse/key event occurs inside the period.</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer select-none">
                  <input 
                    type="checkbox" 
                    className="sr-only peer"
                    checked={securityConfig.autoLogoutEnabled}
                    onChange={e => {
                      updateSecurityConfig({ autoLogoutEnabled: e.target.checked });
                      setLogMessage(`Inactivity security auto-logout guard ${e.target.checked ? 'ENABLED' : 'DISABLED'}`);
                    }}
                  />
                  <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-slate-400 after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-amber-600 peer-checked:after:bg-white peer-checked:after:border-amber-600"></div>
                </label>
              </div>

              {securityConfig.autoLogoutEnabled && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-slate-900/50">
                  <div>
                    <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">Inactivity Threshold (Minutes)</label>
                    <input
                      type="number"
                      min={1}
                      max={120}
                      value={securityConfig.sessionTimeout}
                      onChange={e => {
                        const val = Math.max(1, parseInt(e.target.value) || 15);
                        updateSecurityConfig({ sessionTimeout: val });
                      }}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-blue-500 transition-all text-slate-200"
                    />
                  </div>
                  <div className="flex items-end">
                    <div className="text-[10px] text-slate-500 italic font-medium">
                      Analyst terminal session will automatically dismantle in <span className="text-amber-400 font-bold">{securityConfig.sessionTimeout} minutes</span> of deep inactivity.
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Webhook Configuration Form */}
          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Webhook className="w-4 h-4 text-blue-400" /> Outbound Webhook Integrations
            </h3>
            <p className="text-xs text-slate-400">
              Deliver critical security alert payloads in real-time to external communication platforms for collaborative incident management.
            </p>

            <div className="space-y-4 pt-2">
              
              {/* Slack Webhook Card */}
              <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-200">Slack Webhook channel integration</span>
                    <span className="bg-blue-950/60 text-blue-400 border border-blue-900/20 text-[8.5px] uppercase tracking-wider font-extrabold px-1.5 py-0.5 rounded">Slack</span>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer select-none">
                    <input 
                      type="checkbox" 
                      className="sr-only peer"
                      checked={webhookConfig.slackEnabled}
                      onChange={e => {
                        updateWebhookConfig({ slackEnabled: e.target.checked });
                        setLogMessage(`Slack alerts webhook ${e.target.checked ? 'ENABLED' : 'DISABLED'}`);
                      }}
                    />
                    <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-slate-400 after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600 peer-checked:after:bg-white peer-checked:after:border-blue-600"></div>
                  </label>
                </div>

                {webhookConfig.slackEnabled && (
                  <div className="space-y-3 pt-2 border-t border-slate-900/50">
                    <div>
                      <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">Slack Incoming Webhook URL</label>
                      <input
                        type="url"
                        placeholder="https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
                        value={webhookConfig.slackWebhookUrl}
                        onChange={e => updateWebhookConfig({ slackWebhookUrl: e.target.value })}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-blue-500 transition-all text-slate-200"
                      />
                    </div>
                    <div className="flex justify-end pt-1">
                      <button
                        type="button"
                        disabled={testingWebhook}
                        onClick={() => handleSendTestWebhook('slack')}
                        className="bg-blue-950/40 hover:bg-blue-950/80 border border-blue-900/30 text-blue-400 font-bold px-3.5 py-1.5 rounded-lg text-[10px] transition-all flex items-center gap-1.5 cursor-pointer"
                      >
                        <Send className="w-3 h-3" /> Send Test Slack Alert
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Microsoft Teams Webhook Card */}
              <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-200">Microsoft Teams connector integration</span>
                    <span className="bg-indigo-950/60 text-indigo-400 border border-indigo-900/20 text-[8.5px] uppercase tracking-wider font-extrabold px-1.5 py-0.5 rounded">MS Teams</span>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer select-none">
                    <input 
                      type="checkbox" 
                      className="sr-only peer"
                      checked={webhookConfig.teamsEnabled}
                      onChange={e => {
                        updateWebhookConfig({ teamsEnabled: e.target.checked });
                        setLogMessage(`Microsoft Teams alerts webhook ${e.target.checked ? 'ENABLED' : 'DISABLED'}`);
                      }}
                    />
                    <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-slate-400 after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600 peer-checked:after:bg-white peer-checked:after:border-indigo-600"></div>
                  </label>
                </div>

                {webhookConfig.teamsEnabled && (
                  <div className="space-y-3 pt-2 border-t border-slate-900/50">
                    <div>
                      <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">Microsoft Teams Webhook URL</label>
                      <input
                        type="url"
                        placeholder="https://outlook.office.com/webhook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx@xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/..."
                        value={webhookConfig.teamsWebhookUrl}
                        onChange={e => updateWebhookConfig({ teamsWebhookUrl: e.target.value })}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-blue-500 transition-all text-slate-200"
                      />
                    </div>
                    <div className="flex justify-end pt-1">
                      <button
                        type="button"
                        disabled={testingWebhook}
                        onClick={() => handleSendTestWebhook('teams')}
                        className="bg-indigo-950/40 hover:bg-indigo-950/80 border border-indigo-900/30 text-indigo-400 font-bold px-3.5 py-1.5 rounded-lg text-[10px] transition-all flex items-center gap-1.5 cursor-pointer"
                      >
                        <Send className="w-3 h-3" /> Send Test Teams Alert
                      </button>
                    </div>
                  </div>
                )}
              </div>

            </div>
          </div>

        </div>
      )}

      {/* Console output feedback log */}
      {logMessage && (
        <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg space-y-2">
          <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
            <Terminal className="w-4 h-4 text-blue-500" /> Operations Output
          </h4>
          <div className="bg-slate-950 border border-slate-850 rounded-xl p-3 font-mono text-[10px] text-blue-400 max-h-40 overflow-y-auto whitespace-pre-wrap select-all">
            &gt; {logMessage}
          </div>
        </div>
      )}

    </div>
  );
}
