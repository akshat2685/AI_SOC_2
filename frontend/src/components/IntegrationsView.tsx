'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import IntegrationConnectModal, { Connector, Integration } from '@/components/IntegrationConnectModal';
import {
  Plug,
  Plus,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  MinusCircle,
  Trash2,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Activity,
} from 'lucide-react';

const CATEGORIES = ['All', 'Endpoints', 'SIEM', 'EDR', 'Firewall', 'Identity', 'Cloud', 'Custom'];

interface HealthDetail {
  status: string;
  last_seen_at?: string;
  last_event_at?: string;
  events_received?: number;
  events_rejected?: number;
  error_count?: number;
  last_error?: string;
  data_latency_seconds?: number;
}

function statusStyle(status: string): string {
  const s = (status || '').toUpperCase();
  if (s === 'CONNECTED') return 'text-green-400 bg-green-950/40 border-green-800/50';
  if (s === 'DEGRADED') return 'text-amber-400 bg-amber-950/40 border-amber-800/50';
  if (s === 'DISCONNECTED' || s === 'AUTH ERROR' || s === 'AUTH_ERROR' || s === 'ERROR') return 'text-red-400 bg-red-950/40 border-red-800/50';
  return 'text-slate-400 bg-slate-800/60 border-slate-700/60';
}

function formatStatus(status: string): string {
  return (status || 'NO DATA').toUpperCase().replace(/_/g, ' ');
}

function timeAgo(iso?: string): string {
  if (!iso) return 'never';
  const t = new Date(iso).getTime();
  if (isNaN(t)) return 'never';
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function IntegrationsView() {
  const [catalog, setCatalog] = useState<Connector[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [category, setCategory] = useState('All');
  const [modalConnector, setModalConnector] = useState<Connector | null>(null);
  const [expanded, setExpanded] = useState<string | number | null>(null);
  const [health, setHealth] = useState<Record<string, HealthDetail>>({});
  const [healthLoading, setHealthLoading] = useState<string | number | null>(null);
  const [deleting, setDeleting] = useState<string | number | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    setError('');
    try {
      const [c, list] = await Promise.all([api.getConnectorCatalog(), api.listIntegrations()]);
      setCatalog(c.connectors || []);
      setIntegrations(list.integrations || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load integrations');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, []);

  const filteredCatalog = category === 'All'
    ? catalog
    : catalog.filter(c => (c.category || '').toLowerCase() === category.toLowerCase());

  const toggleHealth = async (integ: Integration) => {
    const id = integ.id;
    if (expanded === id) {
      setExpanded(null);
      return;
    }
    setExpanded(id);
    if (!health[String(id)]) {
      setHealthLoading(id);
      try {
        const h = await api.getIntegrationHealth(id);
        setHealth(prev => ({ ...prev, [String(id)]: h }));
      } catch (e) {
        setHealth(prev => ({ ...prev, [String(id)]: { status: 'ERROR', last_error: e instanceof Error ? e.message : 'Health check failed' } }));
      } finally {
        setHealthLoading(null);
      }
    }
  };

  const handleDelete = async (id: string | number) => {
    if (!window.confirm('Disconnect and delete this integration?')) return;
    setDeleting(id);
    try {
      await api.deleteIntegration(id);
      setIntegrations(prev => prev.filter(i => i.id !== id));
      if (expanded === id) setExpanded(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete integration');
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Plug className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-100">Connect your environment</h1>
            <p className="text-xs text-slate-400">Integrations feed telemetry into EDYSOR — every number below comes from the API, nothing is mocked.</p>
          </div>
        </div>
        <button
          onClick={fetchAll}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold text-slate-300 bg-slate-900 border border-slate-800 hover:bg-slate-800 transition-all"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {error && (
        <div className="mb-4 text-xs bg-red-950/40 border border-red-800/80 text-red-400 px-4 py-3 rounded-xl">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-slate-400 text-sm">
          <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading integrations…
        </div>
      ) : (
        <>
          {/* Connected integrations */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 mb-6">
            <h2 className="text-sm font-bold text-slate-100 mb-1">Connected integrations ({integrations.length})</h2>
            <p className="text-[11px] text-slate-500 mb-4">Expand any row for live health detail.</p>
            {integrations.length === 0 ? (
              <p className="text-xs text-slate-500">Nothing connected yet — pick a connector below to get started.</p>
            ) : (
              <div className="space-y-2">
                {integrations.map(integ => {
                  const isOpen = expanded === integ.id;
                  const h = health[String(integ.id)];
                  return (
                    <div key={String(integ.id)} className="bg-slate-950/60 border border-slate-800 rounded-xl overflow-hidden">
                      <div className="flex items-center gap-3 px-4 py-3">
                        <button onClick={() => toggleHealth(integ)} className="flex-1 flex items-center gap-3 text-left min-w-0">
                          {isOpen ? <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" /> : <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />}
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-semibold text-slate-100 truncate">{integ.name}</p>
                            <p className="text-[11px] text-slate-500">{integ.category} · {integ.connector_key} · last seen {timeAgo(integ.last_seen_at)}</p>
                          </div>
                        </button>
                        <span className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full border ${statusStyle(integ.status)}`}>
                          {formatStatus(integ.status)}
                        </span>
                        <span className="text-[11px] text-slate-400 hidden md:block">{(integ.events_received ?? 0).toLocaleString()} events</span>
                        <button
                          onClick={() => handleDelete(integ.id)}
                          disabled={deleting === integ.id}
                          className="text-slate-500 hover:text-red-400 p-1.5 disabled:opacity-50"
                          title="Disconnect"
                        >
                          {deleting === integ.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                        </button>
                      </div>
                      {isOpen && (
                        <div className="border-t border-slate-800 px-4 py-3">
                          {healthLoading === integ.id ? (
                            <p className="text-xs text-slate-400 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Loading health…</p>
                          ) : h ? (
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                              <HealthStat label="Status" value={formatStatus(h.status)} />
                              <HealthStat label="Last event" value={timeAgo(h.last_event_at)} />
                              <HealthStat label="Events received" value={String(h.events_received ?? 0)} />
                              <HealthStat label="Events rejected" value={String(h.events_rejected ?? 0)} />
                              <HealthStat label="Errors" value={String(h.error_count ?? 0)} />
                              <HealthStat label="Data latency" value={h.data_latency_seconds != null ? `${h.data_latency_seconds}s` : '—'} />
                              <div className="col-span-2">
                                <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Last error</p>
                                <p className="text-slate-300 break-words">{h.last_error || 'None'}</p>
                              </div>
                            </div>
                          ) : (
                            <p className="text-xs text-slate-500">No health data.</p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Category tabs */}
          <div className="flex flex-wrap gap-2 mb-5">
            {CATEGORIES.map(c => (
              <button
                key={c}
                onClick={() => setCategory(c)}
                className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
                  category === c
                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20'
                    : 'bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700'
                }`}
              >
                {c}
              </button>
            ))}
          </div>

          {/* Catalog grid */}
          {filteredCatalog.length === 0 ? (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center">
              <MinusCircle className="w-8 h-8 text-slate-600 mx-auto mb-3" />
              <p className="text-sm text-slate-400">No connectors in this category yet.</p>
            </div>
          ) : (
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredCatalog.map(conn => (
                <div key={conn.key} className="bg-slate-900 border border-slate-800 rounded-2xl p-5 flex flex-col">
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <h3 className="text-sm font-bold text-slate-100">{conn.name}</h3>
                      <p className="text-[11px] text-slate-500">{conn.category} · {conn.connection_method}</p>
                    </div>
                    <div className="w-9 h-9 rounded-lg bg-blue-600/15 border border-blue-500/25 flex items-center justify-center flex-shrink-0">
                      <Plug className="w-4 h-4 text-blue-400" />
                    </div>
                  </div>

                  {conn.capabilities?.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {conn.capabilities.slice(0, 5).map(cap => (
                        <span key={cap} className="text-[10px] bg-slate-800/80 text-slate-300 px-2 py-0.5 rounded-md">{cap}</span>
                      ))}
                    </div>
                  )}

                  {conn.required_permissions?.length > 0 && (
                    <div className="mb-3">
                      <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">Required permissions</p>
                      <ul className="text-[11px] text-slate-400 space-y-0.5">
                        {conn.required_permissions.slice(0, 4).map(p => (
                          <li key={p} className="flex items-center gap-1.5">
                            <span className="w-1 h-1 rounded-full bg-slate-500" /> {p}
                          </li>
                        ))}
                        {conn.required_permissions.length > 4 && (
                          <li className="text-slate-500">+{conn.required_permissions.length - 4} more</li>
                        )}
                      </ul>
                    </div>
                  )}

                  <div className="mt-auto pt-2">
                    <button
                      onClick={() => setModalConnector(conn)}
                      className="w-full flex items-center justify-center gap-2 text-xs font-bold py-2.5 rounded-xl bg-blue-600/20 border border-blue-500/30 text-blue-300 hover:bg-blue-600/30 transition-all"
                    >
                      <Plus className="w-4 h-4" /> Connect
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Legend */}
          <div className="mt-6 flex flex-wrap items-center gap-4 text-[11px] text-slate-500">
            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5 text-green-400" /> Connected</span>
            <span className="flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5 text-amber-400" /> Degraded</span>
            <span className="flex items-center gap-1.5"><XCircle className="w-3.5 h-3.5 text-red-400" /> Disconnected / auth error</span>
            <span className="flex items-center gap-1.5"><Activity className="w-3.5 h-3.5 text-slate-400" /> No data yet</span>
          </div>
        </>
      )}

      <IntegrationConnectModal
        connector={modalConnector}
        onClose={() => setModalConnector(null)}
        onCreated={() => { fetchAll(); }}
      />
    </div>
  );
}

function HealthStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">{label}</p>
      <p className="text-slate-200 font-semibold break-words">{value}</p>
    </div>
  );
}
