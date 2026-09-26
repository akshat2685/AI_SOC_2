/* eslint-disable @typescript-eslint/no-explicit-any */
'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { useStore, Incident } from '@/store/useStore';
import {
  Shield,
  AlertTriangle,
  MonitorSmartphone,
  Plug,
  Brain,
  CheckCircle,
  RefreshCw,
  ChevronRight,
  Radio,
  Unplug,
  Sparkles,
  Clock,
} from 'lucide-react';

interface SOCCommandData {
  incidents_by_severity: { critical: number; high: number; medium: number; low: number };
  alerts: { total: number; critical: number };
  agents: { online: number; offline: number; degraded: number; total: number } | null;
  integrations: { connected: number; degraded: number; disconnected: number; total: number };
  approvals_pending: number;
  derived?: boolean; // true when assembled client-side from other endpoints
}

const SEV_ORDER: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

function sevBadge(sev: string) {
  const s = (sev || '').toUpperCase();
  if (s === 'CRITICAL') return 'bg-red-950/40 text-red-400 border-red-800/30';
  if (s === 'HIGH') return 'bg-orange-950/40 text-orange-400 border-orange-800/30';
  if (s === 'MEDIUM') return 'bg-amber-950/40 text-amber-400 border-amber-800/30';
  return 'bg-blue-950/40 text-blue-400 border-blue-800/30';
}

export default function SOCCommandCenter() {
  const { setActivePage } = useStore();
  const [data, setData] = useState<SOCCommandData | null>(null);
  const [recentIncidents, setRecentIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Preferred: dedicated command-center endpoint (may not exist yet on backend)
      try {
        const soc = await api.getSOCCommand();
        setData({
          incidents_by_severity: {
            critical: Number(soc?.incidents_by_severity?.critical ?? 0),
            high: Number(soc?.incidents_by_severity?.high ?? 0),
            medium: Number(soc?.incidents_by_severity?.medium ?? 0),
            low: Number(soc?.incidents_by_severity?.low ?? 0),
          },
          alerts: {
            total: Number(soc?.alerts?.total ?? 0),
            critical: Number(soc?.alerts?.critical ?? 0),
          },
          agents: soc?.agents
            ? {
                online: Number(soc.agents.online ?? 0),
                offline: Number(soc.agents.offline ?? 0),
                degraded: Number(soc.agents.degraded ?? 0),
                total: Number(soc.agents.total ?? 0),
              }
            : null,
          integrations: {
            connected: Number(soc?.integrations?.connected ?? 0),
            degraded: Number(soc?.integrations?.degraded ?? 0),
            disconnected: Number(soc?.integrations?.disconnected ?? 0),
            total: Number(soc?.integrations?.total ?? 0),
          },
          approvals_pending: Number(soc?.approvals_pending ?? 0),
        });
      } catch {
        // Fallback: derive from existing endpoints — no fabricated numbers.
        const [incidentsRes, alertsRes, approvalsRes, integrationsRes] = await Promise.allSettled([
          api.getIncidents(),
          api.getAlerts(),
          api.getApprovals('PENDING'),
          api.getIntegrationStatus(),
        ]);
        const incidents: any[] = incidentsRes.status === 'fulfilled' ? incidentsRes.value?.incidents ?? incidentsRes.value ?? [] : [];
        const alerts: any[] = alertsRes.status === 'fulfilled' ? alertsRes.value?.alerts ?? alertsRes.value ?? [] : [];
        const approvals: any[] = approvalsRes.status === 'fulfilled' ? approvalsRes.value?.approvals ?? [] : [];
        const integrations: any[] = integrationsRes.status === 'fulfilled' ? integrationsRes.value ?? [] : [];
        const list = Array.isArray(incidents) ? incidents : [];
        const alertList = Array.isArray(alerts) ? alerts : [];
        const countSev = (s: string) => list.filter((i) => (i.severity || '').toUpperCase() === s).length;
        setData({
          incidents_by_severity: {
            critical: countSev('CRITICAL'),
            high: countSev('HIGH'),
            medium: countSev('MEDIUM'),
            low: countSev('LOW'),
          },
          alerts: {
            total: alertList.length,
            critical: alertList.filter((a) => (a.severity || '').toUpperCase() === 'CRITICAL').length,
          },
          agents: null, // no agent endpoint yet — shown as "not connected"
          integrations: {
            connected: integrations.filter((x: any) => x?.status === 'CONNECTED').length,
            degraded: integrations.filter((x: any) => x?.status === 'DEGRADED').length,
            disconnected: integrations.filter((x: any) => x?.status && x.status !== 'CONNECTED' && x.status !== 'DEGRADED').length,
            total: integrations.length,
          },
          approvals_pending: approvals.length,
          derived: true,
        });
      }

      // Recent incidents for the "Active investigations" row
      try {
        const res = await api.getIncidents();
        const list: Incident[] = Array.isArray(res) ? res : res?.incidents ?? [];
        const open = list
          .filter((i) => (i.status || '').toUpperCase() !== 'RESOLVED' && (i.status || '').toUpperCase() !== 'CLOSED')
          .sort((a, b) => (SEV_ORDER[(a.severity || '').toUpperCase()] ?? 9) - (SEV_ORDER[(b.severity || '').toUpperCase()] ?? 9))
          .slice(0, 5);
        setRecentIncidents(open);
      } catch {
        setRecentIncidents([]);
      }
    } catch (e: any) {
      setError(e.message || 'Failed to load SOC command data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500" />
      </div>
    );
  }

  const posture = data?.incidents_by_severity ?? { critical: 0, high: 0, medium: 0, low: 0 };
  const postureCards = [
    { label: 'Critical', value: posture.critical, icon: AlertTriangle, ring: 'border-red-500/30', text: 'text-red-400' },
    { label: 'High', value: posture.high, icon: AlertTriangle, ring: 'border-orange-500/30', text: 'text-orange-400' },
    { label: 'Medium', value: posture.medium, icon: AlertTriangle, ring: 'border-amber-500/30', text: 'text-amber-400' },
    { label: 'Low', value: posture.low, icon: AlertTriangle, ring: 'border-blue-500/30', text: 'text-blue-400' },
  ];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center">
            <Shield className="w-5 h-5 text-blue-400" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-white">SOC Command Center</h2>
            <p className="text-xs text-slate-500">
              Live security posture, fleet health, and AI activity
              {data?.derived && <span className="text-slate-600"> · assembled from live endpoints</span>}
            </p>
          </div>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 text-xs font-semibold bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 px-3 py-2 rounded-lg transition-all"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-950/30 border border-red-800/40 rounded-xl p-4 text-xs text-red-300">
          {error}
        </div>
      )}

      {/* Row 1 — Security posture */}
      <div>
        <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Security Posture</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {postureCards.map((c) => {
            const Icon = c.icon;
            return (
              <button
                key={c.label}
                onClick={() => setActivePage('incidents')}
                className={`bg-slate-900/60 border ${c.ring} rounded-xl p-4 text-left hover:bg-slate-900 transition-all`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{c.label} Incidents</span>
                  <Icon className={`w-4 h-4 ${c.text}`} />
                </div>
                <p className={`text-2xl font-bold font-mono mt-2 ${c.text}`}>{c.value}</p>
              </button>
            );
          })}
          <button
            onClick={() => setActivePage('incidents')}
            className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 text-left hover:bg-slate-900 transition-all"
          >
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Alerts</span>
              <Radio className="w-4 h-4 text-slate-400" />
            </div>
            <p className="text-2xl font-bold font-mono mt-2 text-slate-200">{data?.alerts.total ?? 0}</p>
            <p className="text-[10px] text-slate-500 mt-1">{data?.alerts.critical ?? 0} critical</p>
          </button>
        </div>
      </div>

      {/* Row 2 — Endpoint + integration health */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <MonitorSmartphone className="w-4 h-4 text-emerald-400" />
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">Endpoint Health</h3>
          </div>
          {data?.agents ? (
            <div className="grid grid-cols-4 gap-2 text-center">
              {[
                { label: 'Online', value: data.agents.online, cls: 'text-emerald-400' },
                { label: 'Degraded', value: data.agents.degraded, cls: 'text-amber-400' },
                { label: 'Offline', value: data.agents.offline, cls: 'text-red-400' },
                { label: 'Total', value: data.agents.total, cls: 'text-slate-200' },
              ].map((s) => (
                <div key={s.label} className="bg-slate-950/60 border border-slate-800 rounded-lg p-3">
                  <p className={`text-xl font-bold font-mono ${s.cls}`}>{s.value}</p>
                  <p className="text-[9px] text-slate-500 uppercase tracking-wider mt-1">{s.label}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-3 bg-slate-950/60 border border-dashed border-slate-800 rounded-lg p-4">
              <Unplug className="w-5 h-5 text-slate-600 flex-shrink-0" />
              <p className="text-[11px] text-slate-500">
                No endpoint agents connected. Agent telemetry appears here once the EDYSOR endpoint agent is deployed.
              </p>
            </div>
          )}
        </div>

        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Plug className="w-4 h-4 text-indigo-400" />
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">Integration Health</h3>
          </div>
          <div className="grid grid-cols-4 gap-2 text-center">
            {[
              { label: 'Connected', value: data?.integrations.connected ?? 0, cls: 'text-emerald-400' },
              { label: 'Degraded', value: data?.integrations.degraded ?? 0, cls: 'text-amber-400' },
              { label: 'Down', value: data?.integrations.disconnected ?? 0, cls: 'text-red-400' },
              { label: 'Total', value: data?.integrations.total ?? 0, cls: 'text-slate-200' },
            ].map((s) => (
              <div key={s.label} className="bg-slate-950/60 border border-slate-800 rounded-lg p-3">
                <p className={`text-xl font-bold font-mono ${s.cls}`}>{s.value}</p>
                <p className="text-[9px] text-slate-500 uppercase tracking-wider mt-1">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Connect-your-environment CTA */}
      {(data?.integrations.total ?? 0) === 0 && (
        <div className="bg-gradient-to-r from-blue-950/40 to-indigo-950/40 border border-blue-800/30 rounded-xl p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-bold text-white">Connect your environment</h3>
            <p className="text-xs text-slate-400 mt-1 max-w-xl">
              No integrations connected yet. Connect endpoints, SIEM, EDR, firewall, identity, or cloud sources
              so EDYSOR can discover assets and start monitoring.
            </p>
          </div>
          <button
            onClick={() => setActivePage('settings')}
            className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold px-4 py-2.5 rounded-lg transition-all flex-shrink-0"
          >
            <Plug className="w-4 h-4" />
            Open Integrations
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Row 3 — Active investigations + AI activity */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-blue-400" />
              <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">Active Investigations</h3>
            </div>
            <button
              onClick={() => setActivePage('incidents')}
              className="text-[10px] font-bold text-blue-400 hover:text-blue-300 flex items-center gap-0.5"
            >
              View all <ChevronRight className="w-3 h-3" />
            </button>
          </div>
          {recentIncidents.length === 0 ? (
            <div className="flex items-center gap-2 text-[11px] text-slate-500 py-4">
              <CheckCircle className="w-4 h-4 text-emerald-500" />
              No open incidents. The queue is clear.
            </div>
          ) : (
            <div className="space-y-2">
              {recentIncidents.map((inc) => (
                <button
                  key={inc.id}
                  onClick={() => setActivePage('incidents')}
                  className="w-full flex items-center justify-between gap-3 bg-slate-950/60 border border-slate-800 rounded-lg px-3 py-2.5 hover:border-slate-700 transition-all text-left"
                >
                  <span className="text-[11px] font-semibold text-slate-200 truncate">{inc.title}</span>
                  <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border flex-shrink-0 ${sevBadge(inc.severity)}`}>
                    {inc.severity}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Brain className="w-4 h-4 text-indigo-400" />
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">AI Activity</h3>
          </div>
          <div className="space-y-3">
            <button
              onClick={() => setActivePage('approvals')}
              className="w-full flex items-center justify-between bg-slate-950/60 border border-slate-800 rounded-lg px-4 py-3 hover:border-slate-700 transition-all"
            >
              <span className="text-[11px] font-semibold text-slate-300">Response actions awaiting approval</span>
              <span className={`text-sm font-bold font-mono ${(data?.approvals_pending ?? 0) > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                {data?.approvals_pending ?? 0}
              </span>
            </button>
            <div className="flex items-start gap-2.5 bg-indigo-950/20 border border-indigo-900/30 rounded-lg px-4 py-3">
              <Sparkles className="w-4 h-4 text-indigo-400 flex-shrink-0 mt-0.5" />
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Ask the copilot anything about an incident — <span className="text-slate-300 font-semibold">"What happened?"</span>,{' '}
                <span className="text-slate-300 font-semibold">"Show the attack path"</span> — from the chat button in the bottom-right.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
