'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useStore } from '@/store/useStore';
import {
  Swords,
  RefreshCw,
  Loader2,
  Play,
  Radar,
  ShieldCheck,
  ShieldAlert,
  ChevronDown,
  ChevronRight,
  BrainCircuit,
  Crosshair,
} from 'lucide-react';

// ---- Types mirroring backend/app/sparring/api.py response shapes ----

interface SparringFinding {
  technique_id: string;
  kind: string; // "attack" | "benign"
  detected: boolean;
  detector?: string | null;
  rule_id?: string | null;
  all_rule_ids?: string[];
  events_until_detection?: number | null;
  events_total?: number;
}

interface SparringRun {
  id: string;
  started_at: string;
  finished_at?: string | null;
  duration_s?: number | null;
  technique_count: number;
  detected_count: number;
  evasion_count: number;
  benign_count: number;
  fp_count: number;
  detection_rate: number;
  engine_version?: string;
  model_version?: string;
  findings: SparringFinding[];
}

interface CoverageTechnique {
  technique_id: string;
  runs_tested: number;
  detected: number;
  detection_rate: number | null;
  rules_fired: Record<string, number>;
}

interface CoverageBenign {
  archetype: string;
  runs_tested: number;
  false_positives: number;
  fp_rate: number | null;
}

interface TwinScenarioRow {
  id: number;
  source: string; // "intel-ioc" | "alert-replay" | "simulated-technique"
  technique_id?: string | null;
  tactic?: string | null;
  scenario?: {
    description?: string;
    ioc?: { type?: string; value?: string } | null;
    replay_of_alert_id?: number | null;
    event_count?: number;
  };
  detected: boolean;
  detector?: string | null;
  rule_id?: string | null;
  analysis?: {
    what_happened?: string;
    why_evaded?: string;
    how_to_defend?: string[];
  };
  created_at?: string | null;
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

function pct(rate?: number | null): string {
  if (rate === null || rate === undefined || isNaN(rate)) return '—';
  return `${Math.round(rate * 100)}%`;
}

function sourceLabel(source: string): string {
  if (source === 'intel-ioc') return 'Live intel IoC';
  if (source === 'alert-replay') return 'Real alert replay';
  return 'Simulated technique';
}

export default function TwinView() {
  const { user } = useStore();
  const [runs, setRuns] = useState<SparringRun[]>([]);
  const [techniques, setTechniques] = useState<CoverageTechnique[]>([]);
  const [benign, setBenign] = useState<CoverageBenign[]>([]);
  const [evasionRowsAvailable, setEvasionRowsAvailable] = useState<number | null>(null);
  const [coverageRuns, setCoverageRuns] = useState(0);
  const [scenarios, setScenarios] = useState<TwinScenarioRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<string | null>(null);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const [showAllScenarios, setShowAllScenarios] = useState(false);

  const canRun = ['TENANT_ADMIN', 'TENANT_ANALYST'].includes(
    (user?.role || '').toUpperCase()
  );

  const load = useCallback(async () => {
    setError(null);
    const [runsRes, covRes, scenRes] = await Promise.allSettled([
      api.getSparringRuns(20),
      api.getSparringCoverage(),
      api.getTwinScenarios(50),
    ]);
    if (runsRes.status === 'fulfilled') {
      setRuns(Array.isArray(runsRes.value?.runs) ? runsRes.value.runs : []);
    }
    if (covRes.status === 'fulfilled') {
      setTechniques(Array.isArray(covRes.value?.techniques) ? covRes.value.techniques : []);
      setBenign(Array.isArray(covRes.value?.benign_archetypes) ? covRes.value.benign_archetypes : []);
      setCoverageRuns(covRes.value?.runs_considered ?? 0);
      setEvasionRowsAvailable(covRes.value?.evasion_training_rows_available ?? null);
    }
    if (scenRes.status === 'fulfilled') {
      setScenarios(Array.isArray(scenRes.value?.scenarios) ? scenRes.value.scenarios : []);
    }
    if (runsRes.status === 'rejected' && covRes.status === 'rejected' && scenRes.status === 'rejected') {
      setError(runsRes.reason?.message || 'Failed to load digital twin data');
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runAction = async (kind: 'sparring' | 'intel') => {
    setAction(kind);
    setActionResult(null);
    try {
      if (kind === 'sparring') {
        const r = await api.runSparring();
        setActionResult(
          `Sparring pass complete: ${r.detected_count}/${r.technique_count} techniques detected, ${r.evasion_count} evasions, ${r.fp_count} false positives.`
        );
      } else {
        const r = await api.runTwinIntelPass();
        setActionResult(
          `Intel pass complete: ${r.scenarios_run} scenarios (${r.ioc_scenarios} from live intel IoCs, ${r.replay_scenarios} alert replays), ${r.evasions} evasions, ${r.training_rows_recorded} new training rows recorded.`
        );
      }
      await load();
    } catch (e: any) {
      setActionResult(e?.message || 'Run failed');
    } finally {
      setAction(null);
    }
  };

  const latest = runs[0];
  const evasionScenarios = scenarios.filter(s => !s.detected);
  const visibleScenarios = showAllScenarios ? scenarios : scenarios.slice(0, 12);

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2.5">
            <Swords className="w-5 h-5 text-sky-400" />
            Digital Twin — Live Sparring
          </h1>
          <p className="text-sm text-slate-400 mt-1.5 max-w-3xl">
            The twin attacks a mirror of the detection engine with simulated ATT&amp;CK
            techniques and scenarios built from live threat intel. Every evasion is
            analyzed by the SOC itself and recorded as training data — this is the
            loop that teaches the models. Attacks are simulated and scored in memory;
            no tenant telemetry is touched and findings never become alerts.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setLoading(true); load(); }}
            className="flex items-center gap-2 text-xs font-medium text-slate-300 border border-[#1c2530] hover:border-sky-800 hover:text-sky-300 rounded-md px-3 py-2 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
          {canRun && (
            <>
              <button
                onClick={() => runAction('sparring')}
                disabled={action !== null}
                className="flex items-center gap-2 text-xs font-semibold bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded-md px-3 py-2 transition-colors"
              >
                {action === 'sparring' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                Run sparring pass
              </button>
              <button
                onClick={() => runAction('intel')}
                disabled={action !== null}
                className="flex items-center gap-2 text-xs font-semibold bg-[#131a23] border border-[#243041] hover:border-sky-800 hover:text-sky-300 disabled:opacity-50 text-slate-200 rounded-md px-3 py-2 transition-colors"
              >
                {action === 'intel' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Radar className="w-3.5 h-3.5" />}
                Run intel pass
              </button>
            </>
          )}
        </div>
      </div>

      {actionResult && (
        <div className="text-xs bg-[#0e1319] border border-sky-900/60 text-sky-200 px-4 py-3 rounded-md">
          {actionResult}
        </div>
      )}

      {error && (
        <div className="text-xs bg-red-950/30 border border-red-900/60 text-red-400 px-4 py-3 rounded-md">
          {error}
        </div>
      )}

      {loading && runs.length === 0 && scenarios.length === 0 ? (
        <div className="flex items-center justify-center py-24 text-slate-500">
          <Loader2 className="w-5 h-5 animate-spin mr-3" /> Loading twin data…
        </div>
      ) : (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-[#0e1319] border border-[#1c2530] rounded-lg p-4">
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.14em] flex items-center gap-1.5">
                <Crosshair className="w-3.5 h-3.5" /> Latest run detection
              </p>
              <p className="text-2xl font-bold text-white mt-2">
                {latest ? pct(latest.detection_rate) : '—'}
              </p>
              <p className="text-[11px] text-slate-500 mt-1">
                {latest
                  ? `${latest.detected_count}/${latest.technique_count} techniques · ${timeAgo(latest.started_at)}`
                  : 'No runs yet this session — run a sparring pass'}
              </p>
            </div>
            <div className="bg-[#0e1319] border border-[#1c2530] rounded-lg p-4">
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.14em] flex items-center gap-1.5">
                <ShieldAlert className="w-3.5 h-3.5" /> Evasions (latest run)
              </p>
              <p className="text-2xl font-bold text-white mt-2">
                {latest ? latest.evasion_count : '—'}
              </p>
              <p className="text-[11px] text-slate-500 mt-1">
                {latest ? `${latest.fp_count} false positives on benign traffic` : '—'}
              </p>
            </div>
            <div className="bg-[#0e1319] border border-[#1c2530] rounded-lg p-4">
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.14em] flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5" /> Technique coverage
              </p>
              <p className="text-2xl font-bold text-white mt-2">{techniques.length || '—'}</p>
              <p className="text-[11px] text-slate-500 mt-1">
                techniques tracked across {coverageRuns} recent run{coverageRuns === 1 ? '' : 's'}
              </p>
            </div>
            <div className="bg-[#0e1319] border border-[#1c2530] rounded-lg p-4">
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.14em] flex items-center gap-1.5">
                <BrainCircuit className="w-3.5 h-3.5" /> Evasion training rows
              </p>
              <p className="text-2xl font-bold text-white mt-2">
                {evasionRowsAvailable ?? '—'}
              </p>
              <p className="text-[11px] text-slate-500 mt-1">
                queued for the next gated retrain · {evasionScenarios.length} intel evasions below
              </p>
            </div>
          </div>

          {/* Intel-driven scenarios: the twin vs the newest real attacks */}
          <section className="bg-[#0e1319] border border-[#1c2530] rounded-lg">
            <div className="px-5 py-4 border-b border-[#1c2530]">
              <h2 className="text-sm font-semibold text-white">Twin vs live threat intel</h2>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Scenarios rebuilt from fresh intel IoCs and replays of real high-severity
                alerts, scored by the real engine. Evasions carry the SOC&apos;s own
                analysis: what happened, why it evaded, and how to defend.
              </p>
            </div>
            {scenarios.length === 0 ? (
              <p className="px-5 py-6 text-sm text-slate-500">
                No intel-driven scenarios recorded yet. They are produced by the daily
                background pass{canRun ? ' — or run an intel pass now' : ''}.
              </p>
            ) : (
              <div className="divide-y divide-[#141b26]">
                {visibleScenarios.map(s => (
                  <div key={s.id} className="px-5 py-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded border ${
                        s.detected
                          ? 'text-emerald-400 bg-emerald-950/40 border-emerald-800/50'
                          : 'text-red-400 bg-red-950/40 border-red-800/50'
                      }`}>
                        {s.detected ? 'Detected' : 'Evaded'}
                      </span>
                      <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded border text-slate-300 bg-[#131a23] border-[#243041]">
                        {sourceLabel(s.source)}
                      </span>
                      {s.technique_id && (
                        <span className="text-[11px] font-mono text-sky-300">{s.technique_id}</span>
                      )}
                      {s.tactic && <span className="text-[11px] text-slate-500">{s.tactic}</span>}
                      <span className="text-[11px] text-slate-600 ml-auto">{timeAgo(s.created_at)}</span>
                    </div>
                    <p className="text-sm text-slate-300 mt-2">
                      {s.scenario?.description || 'Scenario'}
                      {s.scenario?.ioc?.value && (
                        <span className="font-mono text-[12px] text-amber-300/90"> · {s.scenario.ioc.type}: {s.scenario.ioc.value}</span>
                      )}
                    </p>
                    <p className="text-[11px] text-slate-500 mt-1">
                      {s.detected
                        ? <>Caught by {s.detector || 'engine'}{s.rule_id ? <> · rule <span className="font-mono">{s.rule_id}</span></> : null}</>
                        : 'Not caught by any detection layer'}
                    </p>
                    {!s.detected && s.analysis && (s.analysis.what_happened || s.analysis.why_evaded || (s.analysis.how_to_defend?.length ?? 0) > 0) && (
                      <div className="mt-3 bg-[#090c11] border border-[#1c2530] rounded-md p-4 space-y-2.5">
                        <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.14em]">
                          SOC self-analysis
                        </p>
                        {s.analysis.what_happened && (
                          <p className="text-xs text-slate-300"><span className="text-slate-500 font-semibold">What happened: </span>{s.analysis.what_happened}</p>
                        )}
                        {s.analysis.why_evaded && (
                          <p className="text-xs text-slate-300"><span className="text-slate-500 font-semibold">Why it evaded: </span>{s.analysis.why_evaded}</p>
                        )}
                        {(s.analysis.how_to_defend?.length ?? 0) > 0 && (
                          <div>
                            <p className="text-xs text-slate-500 font-semibold">How to defend:</p>
                            <ul className="list-disc list-inside text-xs text-slate-300 mt-1 space-y-0.5">
                              {s.analysis.how_to_defend!.map((d, i) => <li key={i}>{d}</li>)}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {scenarios.length > 12 && (
              <button
                onClick={() => setShowAllScenarios(!showAllScenarios)}
                className="w-full text-center text-xs text-sky-400 hover:text-sky-300 py-3 border-t border-[#1c2530]"
              >
                {showAllScenarios ? 'Show fewer' : `Show all ${scenarios.length} scenarios`}
              </button>
            )}
          </section>

          {/* Sparring runs */}
          <section className="bg-[#0e1319] border border-[#1c2530] rounded-lg">
            <div className="px-5 py-4 border-b border-[#1c2530]">
              <h2 className="text-sm font-semibold text-white">Sparring runs</h2>
              <p className="text-[11px] text-slate-500 mt-0.5">
                24 simulated ATT&amp;CK techniques against the live detection engine.
                Runs are held in memory and reset when the backend restarts; the daily
                background pass also runs automatically.
              </p>
            </div>
            {runs.length === 0 ? (
              <p className="px-5 py-6 text-sm text-slate-500">
                No sparring runs recorded since the backend started
                {canRun ? ' — run the first pass with the button above' : ''}.
              </p>
            ) : (
              <div className="divide-y divide-[#141b26]">
                {runs.map(run => {
                  const expanded = expandedRun === run.id;
                  return (
                    <div key={run.id} className="px-5 py-3.5">
                      <button
                        onClick={() => setExpandedRun(expanded ? null : run.id)}
                        className="w-full flex flex-wrap items-center gap-x-4 gap-y-1 text-left"
                      >
                        {expanded
                          ? <ChevronDown className="w-4 h-4 text-slate-500" />
                          : <ChevronRight className="w-4 h-4 text-slate-500" />}
                        <span className="text-sm font-semibold text-white">{pct(run.detection_rate)} detected</span>
                        <span className="text-xs text-slate-400">
                          {run.detected_count}/{run.technique_count} techniques
                        </span>
                        <span className="text-xs text-red-400">{run.evasion_count} evasions</span>
                        <span className="text-xs text-amber-400">{run.fp_count} FPs</span>
                        <span className="text-[11px] text-slate-600 ml-auto">
                          {timeAgo(run.started_at)}
                          {run.duration_s ? ` · ${run.duration_s.toFixed(1)}s` : ''}
                          {run.model_version ? ` · model ${run.model_version}` : ''}
                        </span>
                      </button>
                      {expanded && (
                        <div className="mt-3 ml-8 overflow-x-auto">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-left text-slate-500 border-b border-[#1c2530]">
                                <th className="py-1.5 pr-4 font-semibold">Technique</th>
                                <th className="py-1.5 pr-4 font-semibold">Kind</th>
                                <th className="py-1.5 pr-4 font-semibold">Outcome</th>
                                <th className="py-1.5 pr-4 font-semibold">Detector / rule</th>
                                <th className="py-1.5 font-semibold">Events to detect</th>
                              </tr>
                            </thead>
                            <tbody>
                              {run.findings.map((f, i) => (
                                <tr key={i} className="border-b border-[#111722] text-slate-300">
                                  <td className="py-1.5 pr-4 font-mono text-sky-300">{f.technique_id}</td>
                                  <td className="py-1.5 pr-4">{f.kind}</td>
                                  <td className="py-1.5 pr-4">
                                    <span className={f.detected ? 'text-emerald-400' : (f.kind === 'attack' ? 'text-red-400' : 'text-amber-400')}>
                                      {f.detected ? (f.kind === 'attack' ? 'Detected' : 'False positive') : (f.kind === 'attack' ? 'Evaded' : 'Clean')}
                                    </span>
                                  </td>
                                  <td className="py-1.5 pr-4 font-mono text-[11px]">
                                    {f.detector || '—'}{f.rule_id ? ` · ${f.rule_id}` : ''}
                                  </td>
                                  <td className="py-1.5">
                                    {f.events_until_detection ?? '—'}{f.events_total ? ` / ${f.events_total}` : ''}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* Coverage */}
          <section className="bg-[#0e1319] border border-[#1c2530] rounded-lg">
            <div className="px-5 py-4 border-b border-[#1c2530]">
              <h2 className="text-sm font-semibold text-white">Detection coverage</h2>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Per-technique detection rate across recent runs, measured on simulated
                footprints — honest coverage, not a real-attack guarantee.
              </p>
            </div>
            {techniques.length === 0 ? (
              <p className="px-5 py-6 text-sm text-slate-500">No coverage data yet — run a sparring pass first.</p>
            ) : (
              <div className="px-5 py-4 grid md:grid-cols-2 gap-x-8 gap-y-3">
                {techniques.map(t => (
                  <div key={t.technique_id}>
                    <div className="flex items-baseline justify-between">
                      <span className="text-xs font-mono text-sky-300">{t.technique_id}</span>
                      <span className="text-[11px] text-slate-500">
                        {t.detected}/{t.runs_tested} · <span className="text-slate-300 font-semibold">{pct(t.detection_rate)}</span>
                      </span>
                    </div>
                    <div className="h-1.5 bg-[#131a23] rounded-full mt-1 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${(t.detection_rate ?? 0) >= 0.8 ? 'bg-emerald-500' : (t.detection_rate ?? 0) >= 0.5 ? 'bg-amber-500' : 'bg-red-500'}`}
                        style={{ width: `${Math.round((t.detection_rate ?? 0) * 100)}%` }}
                      />
                    </div>
                    {Object.keys(t.rules_fired || {}).length > 0 && (
                      <p className="text-[10px] text-slate-600 mt-0.5 font-mono">
                        caught by: {Object.entries(t.rules_fired).map(([r, n]) => `${r} ×${n}`).join(', ')}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
            {benign.length > 0 && (
              <div className="px-5 py-3 border-t border-[#1c2530] flex flex-wrap gap-x-6 gap-y-1">
                <span className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider">Benign FP rates:</span>
                {benign.map(b => (
                  <span key={b.archetype} className="text-[11px] text-slate-400">
                    {b.archetype}: <span className="text-slate-200">{pct(b.fp_rate)}</span> ({b.false_positives}/{b.runs_tested})
                  </span>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
