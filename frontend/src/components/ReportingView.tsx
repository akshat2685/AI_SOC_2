'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import {
  Scroll,
  RefreshCw,
  Loader2,
  AlertTriangle,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';

interface AuditEntry {
  id?: number;
  created_at?: string;
  action?: string;
  user_id?: number | null;
  trace_id?: string | null;
  details?: Record<string, unknown>;
  integrity_hash?: string;
}

export default function ReportingView() {
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [chainValid, setChainValid] = useState<boolean | null>(null);
  const [chainError, setChainError] = useState<string | null>(null);
  const [stats, setStats] = useState<any>(null);

  const loadAuditLog = useCallback(async () => {
    setAuditLoading(true);
    try {
      const data = await api.getAuditLog();
      // Backend envelope: { events, chain_valid, chain_error, signing }
      // (older builds returned a bare array — tolerate both)
      const events = Array.isArray(data) ? data : (data?.events ?? []);
      setAuditLog(events);
      setChainValid(typeof data?.chain_valid === 'boolean' ? data.chain_valid : null);
      setChainError(data?.chain_error ?? null);
    } catch (e) {
      console.error('Audit log failed:', e);
    } finally {
      setAuditLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAuditLog();
    api.getStats().then(setStats).catch(() => setStats(null));
  }, [loadAuditLog]);

  const statCards = stats ? [
    { label: 'Incidents in DB', value: Number(stats.active_incidents ?? 0).toLocaleString(), icon: AlertTriangle },
    { label: 'Alerts in DB', value: Number(stats.open_alerts ?? 0).toLocaleString(), icon: ShieldAlert },
    { label: 'Threats blocked', value: Number(stats.threats_blocked ?? 0).toLocaleString(), icon: ShieldCheck },
  ] : [];

  return (
    <div className="p-6 space-y-5 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-100">Audit Log</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Every consequential action taken through this console, recorded with actor and outcome.
          </p>
        </div>
        <button
          onClick={loadAuditLog}
          disabled={auditLoading}
          className="flex items-center gap-1.5 text-xs font-medium bg-[#0e1319] hover:bg-[#111722] border border-[#1c2530] text-slate-300 px-3 py-2 rounded-md transition-colors disabled:opacity-50"
        >
          {auditLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          Refresh
        </button>
      </div>

      {statCards.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {statCards.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.label} className="bg-[#0e1319] border border-[#1c2530] rounded-md p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Icon className="w-3.5 h-3.5 text-slate-500" />
                  <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-[0.14em]">{item.label}</span>
                </div>
                <p className="text-xl font-bold font-mono text-slate-100 tabular-nums">{item.value}</p>
              </div>
            );
          })}
        </div>
      )}

      <div className="bg-[#0e1319] border border-[#1c2530] rounded-md overflow-hidden">
        <div className="px-5 py-3.5 border-b border-[#1a2230] flex items-center gap-2">
          <Scroll className="w-3.5 h-3.5 text-slate-500" />
          <h3 className="text-[10px] font-semibold text-slate-400 uppercase tracking-[0.14em]">Audit trail</h3>
          <span className="ml-auto text-[10px] font-mono text-slate-600">{auditLog.length} entries</span>
          {chainValid !== null && (
            <span className={`text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border ${
              chainValid
                ? 'bg-emerald-950/30 text-emerald-400 border-emerald-900/50'
                : 'bg-red-950/30 text-red-400 border-red-900/50'
            }`} title={chainError ?? 'Tamper-evident hash chain re-verified on read (HMAC-SHA256)'}>
              {chainValid ? 'chain verified' : 'chain broken'}
            </span>
          )}
        </div>
        {auditLog.length > 0 ? (
          <div className="max-h-[560px] overflow-y-auto">
            <table className="w-full">
              <thead className="bg-[#0b0f15] sticky top-0">
                <tr>
                  {['Timestamp', 'Action', 'Actor', 'Trace', 'Hash'].map(h => (
                    <th key={h} className="text-[9px] text-slate-600 font-semibold uppercase tracking-[0.12em] text-left px-4 py-2.5 border-b border-[#1a2230]">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#141b26]">
                {auditLog.slice(0, 200).map((entry, idx) => (
                  <tr key={entry.id ?? idx} className="hover:bg-[#111722] transition-colors">
                    <td className="px-4 py-2.5 text-[11px] text-slate-500 font-mono whitespace-nowrap">
                      {entry.created_at ? new Date(entry.created_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-2.5 text-[11px] text-slate-300 font-medium font-mono">{entry.action || '—'}</td>
                    <td className="px-4 py-2.5 text-[11px] text-slate-400 font-mono">
                      {entry.user_id != null ? `user ${entry.user_id}` : 'system'}
                    </td>
                    <td className="px-4 py-2.5 text-[11px] text-slate-500 font-mono truncate max-w-[160px]">
                      {entry.trace_id || '—'}
                    </td>
                    <td className="px-4 py-2.5 text-[10px] text-slate-600 font-mono truncate max-w-[120px]" title={entry.integrity_hash}>
                      {entry.integrity_hash ? `${entry.integrity_hash.slice(0, 12)}…` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-12 text-slate-600 text-xs">
            {auditLoading ? 'Loading…' : 'No audit entries yet. Actions you take in this console will appear here.'}
          </div>
        )}
      </div>
    </div>
  );
}
