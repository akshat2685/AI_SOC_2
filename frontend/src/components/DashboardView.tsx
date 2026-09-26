'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { useStore, Incident, Alert } from '@/store/useStore';
import {
  ShieldAlert,
  AlertTriangle,
  MonitorSmartphone,
  ShieldCheck,
  FileSpreadsheet,
  RefreshCw,
  Loader2,
  Server,
} from 'lucide-react';
import QuickBlockModal from '@/components/QuickBlockModal';

function sevBadge(sev?: string) {
  const s = (sev || '').toUpperCase();
  if (s === 'CRITICAL') return 'bg-red-950/30 text-red-400 border-red-900/50';
  if (s === 'HIGH') return 'bg-orange-950/30 text-orange-400 border-orange-900/50';
  if (s === 'MEDIUM') return 'bg-amber-950/30 text-amber-400 border-amber-900/50';
  return 'bg-slate-800/40 text-slate-400 border-slate-700/40';
}

function timeAgo(iso?: string | null): string {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (isNaN(t)) return '—';
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function DashboardView() {
  const { incidents, setIncidents, alerts, setAlerts, setActivePage } = useStore();
  const [loading, setLoading] = useState(true);
  const [endpointsOnline, setEndpointsOnline] = useState<number | null>(null);
  const [pendingApprovals, setPendingApprovals] = useState<number | null>(null);
  const [backendHealth, setBackendHealth] = useState<{ status?: string; version?: string } | null>(null);
  const [blockingIp, setBlockingIp] = useState<string | null>(null);
  const [blockReason, setBlockReason] = useState<string>('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [incRes, altRes, agentsRes, apprRes, healthRes] = await Promise.allSettled([
        api.getIncidents(),
        api.getAlerts(),
        api.listAgents(),
        api.getApprovals('PENDING'),
        api.health(),
      ]);
      // Backend already scopes to the signed-in tenant; no client-side filtering theater.
      if (incRes.status === 'fulfilled') {
        const list = Array.isArray(incRes.value) ? incRes.value : incRes.value?.incidents ?? [];
        setIncidents(list);
      }
      if (altRes.status === 'fulfilled') {
        const list = Array.isArray(altRes.value) ? altRes.value : altRes.value?.alerts ?? [];
        setAlerts(list);
      }
      if (agentsRes.status === 'fulfilled' && Array.isArray(agentsRes.value)) {
        setEndpointsOnline(agentsRes.value.filter((a: any) => (a.status || '').toUpperCase() === 'ONLINE').length);
      } else {
        setEndpointsOnline(null);
      }
      if (apprRes.status === 'fulfilled') {
        const list = Array.isArray(apprRes.value) ? apprRes.value : apprRes.value?.approvals ?? [];
        setPendingApprovals(list.length);
      } else {
        setPendingApprovals(null);
      }
      if (healthRes.status === 'fulfilled') {
        setBackendHealth(healthRes.value);
      } else {
        setBackendHealth(null);
      }
    } finally {
      setLoading(false);
    }
  }, [setIncidents, setAlerts]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleDownloadAlertsCSV = () => {
    if (alerts.length === 0) return;
    const headers = ['ID', 'Title', 'Severity', 'Attacker IP', 'Attack Type', 'Verdict', 'Timestamp'];
    const rows = alerts.map((alert: Alert) => [
      alert.id,
      `"${(alert.title || '').replace(/"/g, '""')}"`,
      alert.severity,
      alert.attacker_ip,
      alert.attack_type,
      alert.verdict || 'N/A',
      alert.timestamp || '',
    ]);
    const blob = new Blob([[headers.join(','), ...rows.map(r => r.join(','))].join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `alerts_export_${new Date().toISOString().slice(0, 10)}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const activeIncidents = incidents.filter((i: Incident) => {
    const s = (i.status || '').toUpperCase();
    return s !== 'RESOLVED' && s !== 'CLOSED';
  });
  const recentIncidents = [...activeIncidents]
    .sort((a, b) => new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime())
    .slice(0, 5);

  const kpis = [
    { label: 'Active incidents', value: activeIncidents.length, icon: AlertTriangle, tone: 'text-amber-400', page: 'incidents' as const },
    { label: 'Open alerts', value: alerts.length, icon: ShieldAlert, tone: 'text-red-400', page: 'incidents' as const },
    { label: 'Endpoints online', value: endpointsOnline, icon: MonitorSmartphone, tone: 'text-emerald-400', page: 'endpoints' as const },
    { label: 'Actions awaiting approval', value: pendingApprovals, icon: ShieldCheck, tone: 'text-sky-400', page: 'approvals' as const },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-slate-500 text-sm gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading overview…
      </div>
    );
  }

  return (
    <div className="p-6 space-y-5 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-100">Overview</h2>
          <p className="text-xs text-slate-500 mt-0.5">Live counts from your tenant — nothing here is sampled or estimated.</p>
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-1.5 text-xs font-medium bg-[#0e1319] hover:bg-[#111722] border border-[#1c2530] text-slate-300 px-3 py-2 rounded-md transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </button>
      </div>

      {/* KPI row — all live */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {kpis.map((k) => {
          const Icon = k.icon;
          return (
            <button
              key={k.label}
              onClick={() => setActivePage(k.page)}
              className="bg-[#0e1319] border border-[#1c2530] rounded-md p-4 text-left hover:border-[#243041] transition-colors"
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">{k.label}</span>
                <Icon className={`w-4 h-4 ${k.tone}`} />
              </div>
              <p className="text-2xl font-bold font-mono text-slate-100 mt-2 tabular-nums">
                {k.value === null ? '—' : k.value}
              </p>
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Alerts feed */}
        <div className="lg:col-span-2 bg-[#0e1319] border border-[#1c2530] rounded-md overflow-hidden flex flex-col max-h-[520px]">
          <div className="px-5 py-3.5 border-b border-[#1a2230] flex items-center justify-between">
            <h3 className="text-[10px] font-semibold text-slate-400 uppercase tracking-[0.14em] flex items-center gap-2">
              <ShieldAlert className="w-3.5 h-3.5 text-red-400" /> Latest alerts
            </h3>
            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={handleDownloadAlertsCSV}
                className="flex items-center gap-1.5 text-[10px] font-medium text-slate-400 hover:text-slate-200 border border-[#1c2530] hover:border-[#243041] bg-[#090c11] px-2 py-1 rounded transition-colors"
              >
                <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-500" />
                Export
              </button>
              <span className="text-[10px] font-mono text-slate-500">{alerts.length} total</span>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {alerts.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-slate-600 gap-2">
                <ShieldAlert className="w-7 h-7 opacity-40" />
                <span className="text-xs">No alerts yet.</span>
              </div>
            ) : (
              <div className="divide-y divide-[#141b26]">
                {alerts.slice(0, 10).map((alert: Alert) => (
                  <div key={alert.id} className="px-5 py-3.5 hover:bg-[#111722] transition-colors flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border ${sevBadge(alert.severity)}`}>
                          {alert.severity}
                        </span>
                        <span className="text-xs font-medium text-slate-200 truncate">{alert.title}</span>
                      </div>
                      <p className="text-[11px] text-slate-500 mt-1.5">
                        <button
                          type="button"
                          onClick={() => {
                            setBlockingIp(alert.attacker_ip);
                            setBlockReason(`Triggered by: ${alert.title} (${alert.attack_type})`);
                          }}
                          className="font-mono text-red-400/90 hover:text-red-300 hover:underline bg-red-950/20 px-1.5 py-0.5 rounded border border-red-900/40 transition-colors"
                          title="Block this IP"
                        >
                          {alert.attacker_ip}
                        </button>
                        <span className="mx-2 text-slate-700">·</span>
                        <span className="text-slate-400">{alert.attack_type}</span>
                      </p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <span className="text-[10px] font-mono text-slate-500">{timeAgo(alert.timestamp)}</span>
                      {alert.verdict && (
                        <p className="text-[9px] font-semibold text-emerald-400 mt-1 uppercase tracking-wide">{alert.verdict}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-4">
          {/* Backend status — real liveness probe */}
          <div className="bg-[#0e1319] border border-[#1c2530] rounded-md p-5">
            <h3 className="text-[10px] font-semibold text-slate-400 uppercase tracking-[0.14em] flex items-center gap-2 mb-4">
              <Server className="w-3.5 h-3.5 text-slate-500" /> Backend
            </h3>
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">API status</span>
              {backendHealth ? (
                <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  {(backendHealth.status || 'ok').toUpperCase()}
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-xs font-medium text-red-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                  UNREACHABLE
                </span>
              )}
            </div>
            {backendHealth?.version && (
              <div className="flex items-center justify-between mt-2.5">
                <span className="text-xs text-slate-400">Version</span>
                <span className="text-xs font-mono text-slate-300">{backendHealth.version}</span>
              </div>
            )}
            <p className="text-[10px] text-slate-600 mt-3 leading-relaxed">
              Live probe of the API backing this console. Infrastructure beyond the API is not instrumented here.
            </p>
          </div>

          {/* Recent incidents */}
          <div className="bg-[#0e1319] border border-[#1c2530] rounded-md p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[10px] font-semibold text-slate-400 uppercase tracking-[0.14em]">Recent incidents</h3>
              <button
                onClick={() => setActivePage('incidents')}
                className="text-[10px] font-medium text-sky-400 hover:text-sky-300"
              >
                View all
              </button>
            </div>
            {recentIncidents.length === 0 ? (
              <p className="text-[11px] text-slate-600 py-3">No open incidents. The queue is clear.</p>
            ) : (
              <div className="space-y-2">
                {recentIncidents.map((inc: Incident) => (
                  <button
                    key={inc.id}
                    onClick={() => setActivePage('incidents')}
                    className="w-full flex items-center justify-between gap-3 bg-[#090c11] border border-[#1c2530] rounded-md px-3 py-2.5 hover:border-[#243041] transition-colors text-left"
                  >
                    <span className="text-[11px] font-medium text-slate-300 truncate">{inc.title}</span>
                    <span className={`text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border flex-shrink-0 ${sevBadge(inc.severity)}`}>
                      {inc.severity}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <QuickBlockModal
        isOpen={blockingIp !== null}
        onClose={() => setBlockingIp(null)}
        ipAddress={blockingIp || ''}
        initialReason={blockReason}
      />
    </div>
  );
}
