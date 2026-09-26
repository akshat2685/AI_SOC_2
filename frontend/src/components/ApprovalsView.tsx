/* eslint-disable @typescript-eslint/no-explicit-any */
'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useStore } from '@/store/useStore';
import {
  ShieldCheck,
  Check,
  X,
  RefreshCw,
  Clock,
  ChevronDown,
  AlertTriangle,
  ArrowUpCircle,
  Info,
  Zap,
} from 'lucide-react';

type Approval = {
  id: number;
  execution_id: number;
  playbook_id: number;
  playbook_name: string;
  status: string;
  requester_id: number | null;
  approver_id: number | null;
  context: Record<string, any>;
  created_at: string | null;
};

const FILTERS = ['ALL', 'PENDING', 'APPROVED', 'REJECTED'] as const;

const AUTONOMY_MODES = [
  { id: 'advisory', label: 'Advisory', desc: 'AI recommends, human decides every action' },
  { id: 'assisted', label: 'Assisted', desc: 'AI acts on low-risk, asks on high-risk' },
  { id: 'controlled', label: 'Controlled', desc: 'AI executes within policy guardrails' },
] as const;

function statusStyle(status: string) {
  switch (status) {
    case 'PENDING':
      return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
    case 'APPROVED':
      return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
    case 'REJECTED':
      return 'bg-red-500/10 text-red-400 border-red-500/30';
    default:
      return 'bg-slate-500/10 text-slate-400 border-slate-500/30';
  }
}

function fmtConfidence(v: any): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') {
    return v <= 1 ? `${Math.round(v * 100)}%` : `${v}%`;
  }
  return String(v);
}

function field(ctx: Record<string, any>, ...keys: string[]): string {
  for (const k of keys) {
    const v = ctx?.[k];
    if (v !== null && v !== undefined && v !== '') return String(v);
  }
  return '—';
}

export default function ApprovalsView() {
  const { user } = useStore();
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('PENDING');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actingId, setActingId] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  // Escalation has no backend endpoint yet — tracked locally and labeled honestly.
  const [escalatedIds, setEscalatedIds] = useState<Set<number>>(new Set());

  const isAdmin = user?.role === 'TENANT_ADMIN' || user?.role === 'GLOBAL_ADMIN';

  const load = async (f: (typeof FILTERS)[number] = filter) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getApprovals(f);
      setApprovals(res.approvals || []);
    } catch (e: any) {
      setError(e.message || 'Failed to load approvals');
      setApprovals([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(filter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  const decide = async (id: number, action: 'approve' | 'reject') => {
    setActingId(id);
    setError(null);
    try {
      if (action === 'approve') {
        await api.approveApproval(id);
      } else {
        await api.rejectApproval(id);
      }
      await load();
    } catch (e: any) {
      setError(e.message || `Failed to ${action} request`);
    } finally {
      setActingId(null);
    }
  };

  const escalate = (id: number) => {
    setEscalatedIds((prev) => new Set(prev).add(id));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-md bg-[#131a23] border border-[#243041] flex items-center justify-center">
            <ShieldCheck className="w-5 h-5 text-sky-400" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-100">Response Center</h2>
            <p className="text-xs text-slate-500">
              Human decisions on AI-proposed response actions
              {user?.role ? ` · signed in as ${user.role}` : ''}
            </p>
          </div>
        </div>
        <button
          onClick={() => load()}
          disabled={loading}
          className="flex items-center gap-1.5 text-xs font-semibold bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 px-3 py-2 rounded-md transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Autonomy mode banner — policy display only */}
      <div className="bg-[#0e1319] border border-[#1c2530] rounded-md p-4">
        <div className="flex items-start gap-2.5">
          <Info className="w-4 h-4 text-slate-500 mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-[11px] font-bold text-slate-300">
              Autonomy mode <span className="font-normal text-slate-500">· policy display only — not enforced by this UI</span>
            </p>
            <div className="flex flex-wrap gap-2 mt-2.5">
              {AUTONOMY_MODES.map((m) => (
                <div
                  key={m.id}
                  className="flex items-center gap-2 bg-[#090c11] border border-[#1c2530] rounded-md px-3 py-2"
                  title={m.desc}
                >
                  <Zap className="w-3.5 h-3.5 text-slate-500" />
                  <div>
                    <p className="text-[11px] font-bold text-slate-300">{m.label}</p>
                    <p className="text-[9px] text-slate-600">{m.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-xs font-bold px-3.5 py-2 rounded-md border transition-all ${
              filter === f
                ? 'bg-sky-600/20 border-sky-500/40 text-blue-300'
                : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-start gap-2.5 bg-red-950/30 border border-red-800/40 rounded-md p-4 text-xs text-red-300">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-bold">Request failed</p>
            <p className="text-red-400/80 mt-0.5">{error}</p>
            {error.includes('403') || error.toLowerCase().includes('forbidden') || error.toLowerCase().includes('role') ? (
              <p className="text-red-400/80 mt-1">
                Viewing the queue needs an analyst or admin role; approving needs a tenant admin.
              </p>
            ) : null}
          </div>
        </div>
      )}

      {/* Queue */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-sky-500" />
        </div>
      ) : approvals.length === 0 ? (
        <div className="bg-slate-900/60 border border-dashed border-slate-800 rounded-2xl p-12 text-center">
          <Clock className="w-8 h-8 text-slate-600 mx-auto mb-3" />
          <p className="text-sm font-semibold text-slate-400">No {filter === 'ALL' ? '' : filter.toLowerCase() + ' '}response actions</p>
          <p className="text-xs text-slate-600 mt-1">
            Requests appear here when a SOAR playbook pauses for human review.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {approvals.map((a) => {
            const ctx = a.context || {};
            const escalated = escalatedIds.has(a.id);
            return (
              <div
                key={a.id}
                className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 hover:border-slate-700 transition-all"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <h3 className="text-sm font-bold text-slate-100 truncate">{a.playbook_name}</h3>
                      <span
                        className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${statusStyle(a.status)}`}
                      >
                        {a.status}
                      </span>
                      {escalated && (
                        <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border bg-purple-500/10 text-purple-300 border-purple-500/30">
                          Escalated
                        </span>
                      )}
                    </div>
                    {/* ACTION / WHY / ASSET / RISK / CONFIDENCE / POLICY */}
                    <dl className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2.5 mt-3">
                      <div>
                        <dt className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Action</dt>
                        <dd className="text-[11px] text-slate-200 mt-0.5 font-mono">{a.playbook_name}</dd>
                      </div>
                      <div>
                        <dt className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Why</dt>
                        <dd className="text-[11px] text-slate-300 mt-0.5" title={field(ctx, 'reason', 'why', 'description')}>
                          <span className="line-clamp-2">{field(ctx, 'reason', 'why', 'description')}</span>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Affected asset</dt>
                        <dd className="text-[11px] text-slate-200 mt-0.5 font-mono">{field(ctx, 'asset', 'target', 'hostname', 'host', 'ip', 'source_ip')}</dd>
                      </div>
                      <div>
                        <dt className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Risk</dt>
                        <dd className="text-[11px] text-slate-200 mt-0.5">{field(ctx, 'risk', 'risk_level', 'severity')}</dd>
                      </div>
                      <div>
                        <dt className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">AI confidence</dt>
                        <dd className="text-[11px] text-slate-200 mt-0.5 font-mono">{fmtConfidence(ctx.confidence ?? ctx.ai_confidence)}</dd>
                      </div>
                      <div>
                        <dt className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Policy</dt>
                        <dd className="text-[11px] text-slate-200 mt-0.5">{field(ctx, 'policy', 'policy_name')}</dd>
                      </div>
                    </dl>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2.5 text-[10px] text-slate-600">
                      <span>
                        Request <span className="font-mono text-slate-500">#{a.id}</span>
                      </span>
                      <span>
                        Execution <span className="font-mono text-slate-500">#{a.execution_id}</span>
                      </span>
                      {a.created_at && <span>{new Date(a.created_at).toLocaleString()}</span>}
                      {a.approver_id != null && (
                        <span>
                          Decided by <span className="font-mono text-slate-500">#{a.approver_id}</span>
                        </span>
                      )}
                    </div>
                  </div>

                  {a.status === 'PENDING' && (
                    <div className="flex gap-2 flex-shrink-0">
                      <button
                        onClick={() => decide(a.id, 'approve')}
                        disabled={!isAdmin || actingId === a.id}
                        title={isAdmin ? 'Approve this action' : 'Tenant admin role required'}
                        className="flex items-center gap-1.5 text-xs font-bold bg-emerald-600/20 hover:bg-emerald-600/30 disabled:opacity-40 disabled:cursor-not-allowed border border-emerald-500/40 text-emerald-300 px-3 py-2 rounded-md transition-all"
                      >
                        <Check className="w-3.5 h-3.5" />
                        {actingId === a.id ? 'Working...' : 'Approve'}
                      </button>
                      <button
                        onClick={() => decide(a.id, 'reject')}
                        disabled={!isAdmin || actingId === a.id}
                        title={isAdmin ? 'Reject this action' : 'Tenant admin role required'}
                        className="flex items-center gap-1.5 text-xs font-bold bg-red-600/20 hover:bg-red-600/30 disabled:opacity-40 disabled:cursor-not-allowed border border-red-500/40 text-red-300 px-3 py-2 rounded-md transition-all"
                      >
                        <X className="w-3.5 h-3.5" />
                        Reject
                      </button>
                      <button
                        onClick={() => escalate(a.id)}
                        disabled={!isAdmin || actingId === a.id || escalated}
                        title={
                          escalated
                            ? 'Already escalated (tracked locally — no backend escalate endpoint yet)'
                            : isAdmin
                              ? 'Escalate to SOC manager (tracked locally — no backend escalate endpoint yet)'
                              : 'Tenant admin role required'
                        }
                        className="flex items-center gap-1.5 text-xs font-bold bg-purple-600/20 hover:bg-purple-600/30 disabled:opacity-40 disabled:cursor-not-allowed border border-purple-500/40 text-purple-300 px-3 py-2 rounded-md transition-all"
                      >
                        <ArrowUpCircle className="w-3.5 h-3.5" />
                        {escalated ? 'Escalated' : 'Escalate'}
                      </button>
                    </div>
                  )}
                </div>

                {/* Context toggle */}
                {a.context && Object.keys(a.context).length > 0 && (
                  <div className="mt-3">
                    <button
                      onClick={() => setExpandedId(expandedId === a.id ? null : a.id)}
                      className="flex items-center gap-1 text-[11px] font-semibold text-slate-500 hover:text-slate-300 transition-colors"
                    >
                      <ChevronDown
                        className={`w-3.5 h-3.5 transition-transform ${expandedId === a.id ? 'rotate-180' : ''}`}
                      />
                      Full execution context
                    </button>
                    {expandedId === a.id && (
                      <pre className="mt-2 bg-slate-950 border border-[#1c2530] rounded-md p-3 text-[10px] font-mono text-slate-400 overflow-x-auto max-h-48 overflow-y-auto">
                        {JSON.stringify(a.context, null, 2)}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
