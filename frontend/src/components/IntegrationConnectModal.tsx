'use client';

import React, { useState } from 'react';
import { api, API_BASE_URL } from '@/lib/api';
import { X, Plug, CheckCircle2, XCircle, Loader2, Eye, EyeOff } from 'lucide-react';

export interface Connector {
  key: string;
  name: string;
  category: string;
  connection_method: string;
  capabilities: string[];
  required_permissions: string[];
  data_collected: string[];
}

export interface Integration {
  id: string | number;
  name: string;
  category: string;
  connector_key: string;
  status: string;
  last_seen_at?: string;
  last_event_at?: string;
  events_received?: number;
  events_rejected?: number;
  error_count?: number;
}

interface CheckResult {
  name: string;
  passed: boolean;
  detail?: string;
}

function isSecretField(name: string): boolean {
  const n = name.toLowerCase();
  return n.includes('password') || n.includes('secret') || n.includes('token') || n.includes('key') || n.includes('credential');
}

function prettyField(name: string): string {
  return name.replace(/[_-]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

interface Props {
  connector: Connector | null;
  onClose: () => void;
  onCreated: (integration: Integration) => void;
}

export default function IntegrationConnectModal({ connector, onClose, onCreated }: Props) {
  const [name, setName] = useState('');
  const [config, setConfig] = useState<Record<string, string>>({});
  const [showSecrets, setShowSecrets] = useState(false);
  const [creating, setCreating] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState('');
  const [created, setCreated] = useState<Integration | null>(null);
  const [checks, setChecks] = useState<CheckResult[] | null>(null);
  const [testNote, setTestNote] = useState('');

  if (!connector) return null;

  const fields = connector.required_permissions || [];

  const handleCreate = async () => {
    setError('');
    setCreating(true);
    try {
      const integration = await api.createIntegration({
        name: name.trim() || connector.name,
        category: connector.category,
        connector_key: connector.key,
        config,
      });
      setCreated(integration);
      onCreated(integration);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create integration');
    } finally {
      setCreating(false);
    }
  };

  const handleTest = async () => {
    if (!created) return;
    setTesting(true);
    setChecks(null);
    try {
      const res = await api.testIntegration(created.id);
      setChecks(res.checks || []);
      setTestNote(res.note || '');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Test failed');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center">
              <Plug className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-100">Connect {connector.name}</h3>
              <p className="text-[11px] text-slate-400">{connector.category} · {connector.connection_method}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {!created ? (
            <>
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">Integration name</label>
                <input
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder={connector.name}
                  className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/80"
                />
              </div>

              {fields.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Credentials & settings</span>
                    <button
                      type="button"
                      onClick={() => setShowSecrets(!showSecrets)}
                      className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center gap-1"
                    >
                      {showSecrets ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                      {showSecrets ? 'Hide secrets' : 'Show secrets'}
                    </button>
                  </div>
                  {fields.map(f => {
                    const secret = isSecretField(f);
                    return (
                      <div key={f}>
                        <label className="block text-xs text-slate-400 mb-1.5">{prettyField(f)}{secret && ' · secret'}</label>
                        <input
                          type={secret && !showSecrets ? 'password' : 'text'}
                          value={config[f] || ''}
                          onChange={e => setConfig(prev => ({ ...prev, [f]: e.target.value }))}
                          autoComplete="off"
                          className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/80"
                        />
                      </div>
                    );
                  })}
                  <p className="text-[11px] text-slate-500">Secrets are sent to the backend only and are never displayed back or logged.</p>
                </div>
              )}

              {connector.data_collected?.length > 0 && (
                <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-3">
                  <p className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider mb-2">Data collected</p>
                  <div className="flex flex-wrap gap-1.5">
                    {connector.data_collected.map(d => (
                      <span key={d} className="text-[11px] bg-slate-800/80 text-slate-300 px-2 py-1 rounded-md">{d}</span>
                    ))}
                  </div>
                </div>
              )}

              {error && (
                <div className="text-xs bg-red-950/40 border border-red-800/80 text-red-400 px-4 py-3 rounded-xl">{error}</div>
              )}

              <button
                onClick={handleCreate}
                disabled={creating}
                className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold py-3 rounded-xl transition-all disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {creating && <Loader2 className="w-4 h-4 animate-spin" />}
                {creating ? 'Connecting…' : 'Connect'}
              </button>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 text-green-400 text-sm font-semibold">
                <CheckCircle2 className="w-5 h-5" /> Connected — ID {String(created.id)}
              </div>

              <button
                onClick={handleTest}
                disabled={testing}
                className="w-full bg-slate-800 hover:bg-slate-700 text-slate-100 font-semibold py-2.5 rounded-xl transition-all disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {testing && <Loader2 className="w-4 h-4 animate-spin" />}
                {testing ? 'Testing…' : 'Test Connection'}
              </button>

              {checks && (
                <div className="space-y-2">
                  {checks.map((c, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs bg-slate-950/60 border border-slate-800 rounded-lg px-3 py-2">
                      {c.passed ? <CheckCircle2 className="w-4 h-4 text-green-400 flex-shrink-0 mt-0.5" /> : <XCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />}
                      <div>
                        <p className="font-semibold text-slate-200">{c.name}</p>
                        {c.detail && <p className="text-slate-400 mt-0.5">{c.detail}</p>}
                      </div>
                    </div>
                  ))}
                  {testNote && <p className="text-[11px] text-slate-500">{testNote}</p>}
                </div>
              )}

              {error && (
                <div className="text-xs bg-red-950/40 border border-red-800/80 text-red-400 px-4 py-3 rounded-xl">{error}</div>
              )}

              <button
                onClick={onClose}
                className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold py-3 rounded-xl transition-all"
              >
                Done
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function backendUrlForSnippet(): string {
  return API_BASE_URL || 'https://<your-backend-host>';
}
