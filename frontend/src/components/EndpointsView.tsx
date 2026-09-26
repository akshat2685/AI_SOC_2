'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import {
  MonitorSmartphone,
  RefreshCw,
  Loader2,
  Plus,
  Cpu,
  Globe,
} from 'lucide-react';
import { useStore } from '@/store/useStore';

interface EndpointAgent {
  id: string;
  device_id: string;
  hostname: string;
  platform?: string | null;
  os_version?: string | null;
  arch?: string | null;
  agent_version?: string | null;
  ip_address?: string | null;
  status?: string | null;
  last_heartbeat_at?: string | null;
  registered_at?: string | null;
}

function statusStyle(status?: string | null): string {
  const s = (status || '').toUpperCase();
  if (s === 'ONLINE') return 'text-emerald-400 bg-emerald-950/40 border-emerald-800/50';
  if (s === 'DEGRADED') return 'text-amber-400 bg-amber-950/40 border-amber-800/50';
  if (s === 'OFFLINE') return 'text-red-400 bg-red-950/40 border-red-800/50';
  return 'text-slate-400 bg-slate-800/60 border-slate-700/60';
}

function platformIcon(platform?: string | null) {
  const p = (platform || '').toLowerCase();
  // Single generic endpoint icon keeps this honest across platforms.
  return <MonitorSmartphone className="w-5 h-5 text-sky-400" />;
}

function timeAgo(iso?: string | null): string {
  if (!iso) return 'never';
  const t = new Date(iso).getTime();
  if (isNaN(t)) return 'never';
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function EndpointsView() {
  const { setActivePage } = useStore();
  const [agents, setAgents] = useState<EndpointAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await api.listAgents();
      setAgents(Array.isArray(list) ? list : []);
    } catch (e: any) {
      setError(e?.message || 'Failed to load endpoint agents');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const online = agents.filter(a => (a.status || '').toUpperCase() === 'ONLINE').length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Endpoints</h1>
          <p className="text-sm text-slate-400 mt-1">
            Machines enrolled with the EDYSOR telemetry sensor — live status from heartbeat age.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400">
            <span className="text-emerald-400 font-semibold">{online}</span> online of{' '}
            <span className="text-slate-200 font-semibold">{agents.length}</span> total
          </span>
          <button
            onClick={load}
            className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg bg-slate-800/60 border border-slate-700/60 text-slate-300 hover:bg-slate-800 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={() => setActivePage('onboarding')}
            className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white transition"
          >
            <Plus className="w-3.5 h-3.5" />
            Enroll endpoint
          </button>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16 text-slate-400 text-sm gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading endpoints…
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl border border-red-800/50 bg-red-950/30 text-red-300 text-sm">
          {error}
        </div>
      )}

      {!loading && !error && agents.length === 0 && (
        <div className="py-16 text-center border border-dashed border-slate-800 rounded-2xl">
          <MonitorSmartphone className="w-10 h-10 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-300 font-medium">No endpoint agents enrolled yet</p>
          <p className="text-slate-500 text-sm mt-1">
            Install the sensor on a machine to see it here with live status.
          </p>
          <button
            onClick={() => setActivePage('onboarding')}
            className="mt-4 text-xs px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white transition"
          >
            Open the Endpoints setup step
          </button>
        </div>
      )}

      {!loading && !error && agents.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {agents.map((a) => (
            <div
              key={a.device_id}
              className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800/80 hover:border-slate-700 transition"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-10 h-10 rounded-xl bg-slate-800/80 border border-slate-700/60 flex items-center justify-center shrink-0">
                    {platformIcon(a.platform)}
                  </div>
                  <div className="min-w-0">
                    <p className="text-slate-100 font-semibold truncate">{a.hostname || a.device_id}</p>
                    <p className="text-[11px] text-slate-500 font-mono truncate">{a.device_id}</p>
                  </div>
                </div>
                <span className={`text-[10px] font-semibold uppercase tracking-wide px-2 py-1 rounded-md border ${statusStyle(a.status)}`}>
                  {a.status || 'unknown'}
                </span>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                <div className="flex items-center gap-1.5 text-slate-400">
                  <Cpu className="w-3.5 h-3.5 text-slate-500" />
                  <span className="capitalize">{a.platform || '—'}</span>
                  {a.arch && <span className="text-slate-600">· {a.arch}</span>}
                </div>
                <div className="flex items-center gap-1.5 text-slate-400">
                  <Globe className="w-3.5 h-3.5 text-slate-500" />
                  <span className="font-mono">{a.ip_address || '—'}</span>
                </div>
                <div className="text-slate-500 col-span-2 truncate">
                  {a.os_version || 'OS version unknown'}
                  {a.agent_version && <span className="text-slate-600"> · sensor {a.agent_version}</span>}
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px]">
                <span className="text-slate-500">
                  Heartbeat: <span className="text-slate-300">{timeAgo(a.last_heartbeat_at)}</span>
                </span>
                <span className="text-slate-600">
                  enrolled {timeAgo(a.registered_at)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
