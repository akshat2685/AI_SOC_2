'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { useStore } from '@/store/useStore';
import {
  Key,
  Plus,
  Copy,
  Check,
  Trash2,
  Shield,
  Loader2,
  RefreshCw,
  Sun,
  Moon,
  Monitor,
  AlertTriangle,
} from 'lucide-react';

interface ApiKey {
  id: string;
  name: string;
  key_prefix?: string;
  is_active?: boolean;
  created_at?: string;
  last_used_at?: string | null;
  revoked_at?: string | null;
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

function Section({ title, desc, children }: { title: string; desc: string; children: React.ReactNode }) {
  return (
    <div className="bg-[#0e1319] border border-[#1c2530] rounded-md p-5">
      <h3 className="text-[10px] font-semibold text-slate-400 uppercase tracking-[0.14em] mb-1">{title}</h3>
      <p className="text-[11px] text-slate-500 mb-4 leading-relaxed">{desc}</p>
      {children}
    </div>
  );
}

export default function SettingsView() {
  const { themeMode, setThemeMode } = useStore();

  // API keys
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [keysLoading, setKeysLoading] = useState(true);
  const [newKeyName, setNewKeyName] = useState('');
  const [creating, setCreating] = useState(false);
  const [freshKey, setFreshKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);

  // Firewall blocks
  const [blocks, setBlocks] = useState<any[]>([]);
  const [blocksLoading, setBlocksLoading] = useState(true);
  const [unblocking, setUnblocking] = useState<string | null>(null);

  const loadKeys = useCallback(async () => {
    setKeysLoading(true);
    try {
      const res = await api.listApiKeys();
      setKeys(Array.isArray(res) ? res : []);
    } catch {
      setKeys([]);
    } finally {
      setKeysLoading(false);
    }
  }, []);

  const loadBlocks = useCallback(async () => {
    setBlocksLoading(true);
    try {
      const res = await api.getFirewallBlocks();
      setBlocks(Array.isArray(res) ? res : res?.blocks ?? []);
    } catch {
      setBlocks([]);
    } finally {
      setBlocksLoading(false);
    }
  }, []);

  useEffect(() => {
    loadKeys();
    loadBlocks();
  }, [loadKeys, loadBlocks]);

  const handleCreateKey = async () => {
    const name = newKeyName.trim();
    if (!name) return;
    setCreating(true);
    setFreshKey(null);
    try {
      const res = await api.createApiKey(name, []);
      if (res?.raw_key) {
        setFreshKey(res.raw_key);
        setCopied(false);
      }
      setNewKeyName('');
      await loadKeys();
    } catch (e: any) {
      alert(e?.message || 'Failed to create API key');
    } finally {
      setCreating(false);
    }
  };

  const handleCopyKey = async () => {
    if (!freshKey) return;
    try {
      await navigator.clipboard.writeText(freshKey);
      setCopied(true);
    } catch {
      /* clipboard unavailable */
    }
  };

  const handleRevoke = async (id: string, name: string) => {
    if (!confirm(`Revoke API key "${name}"? Sensors using it will stop authenticating.`)) return;
    setRevoking(id);
    try {
      await api.revokeApiKey(id);
      await loadKeys();
    } catch (e: any) {
      alert(e?.message || 'Failed to revoke API key');
    } finally {
      setRevoking(null);
    }
  };

  const handleUnblock = async (ip: string) => {
    setUnblocking(ip);
    try {
      await api.unblockIp(ip);
      await loadBlocks();
    } catch (e: any) {
      alert(e?.message || 'Failed to unblock IP');
    } finally {
      setUnblocking(null);
    }
  };

  return (
    <div className="p-6 space-y-5 max-w-4xl mx-auto">
      <div>
        <h2 className="text-lg font-bold text-slate-100">Settings</h2>
        <p className="text-xs text-slate-500 mt-0.5">API keys, firewall blocks, and console preferences.</p>
      </div>

      {/* API Keys */}
      <Section
        title="API Keys"
        desc="Keys authenticate sensors and integrations via the X-API-Key header. The full key is shown once at creation — copy it immediately."
      >
        {freshKey && (
          <div className="mb-4 p-4 rounded-md bg-amber-950/20 border border-amber-900/40">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-400 mb-2">
              New key — copy now, it won't be shown again
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs font-mono text-amber-200 bg-[#090c11] border border-amber-900/40 rounded px-3 py-2 break-all select-all">
                {freshKey}
              </code>
              <button
                onClick={handleCopyKey}
                className="flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-md bg-amber-600/20 border border-amber-800/50 text-amber-300 hover:bg-amber-600/30 transition-colors flex-shrink-0"
              >
                {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>
        )}

        <div className="flex gap-2 mb-4">
          <input
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreateKey()}
            placeholder="Key name, e.g. windows-sensor"
            className="flex-1 bg-[#090c11] border border-[#1c2530] rounded-md px-3 py-2 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-sky-500/70"
          />
          <button
            onClick={handleCreateKey}
            disabled={creating || !newKeyName.trim()}
            className="flex items-center gap-1.5 text-xs font-medium px-4 py-2 rounded-md bg-sky-600 hover:bg-sky-500 text-white transition-colors disabled:opacity-50"
          >
            {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            Create key
          </button>
        </div>

        {keysLoading ? (
          <div className="flex items-center gap-2 text-xs text-slate-500 py-4">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading keys…
          </div>
        ) : keys.length === 0 ? (
          <p className="text-[11px] text-slate-600 py-3">No API keys yet. Create one to enroll a sensor.</p>
        ) : (
          <div className="divide-y divide-[#141b26] border border-[#1c2530] rounded-md overflow-hidden">
            {keys.map((k) => {
              const revoked = !!k.revoked_at || k.is_active === false;
              return (
                <div key={k.id} className="flex items-center justify-between gap-3 px-4 py-3 bg-[#090c11]">
                  <div className="flex items-center gap-3 min-w-0">
                    <Key className={`w-4 h-4 flex-shrink-0 ${revoked ? 'text-slate-600' : 'text-sky-400'}`} />
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-slate-200 truncate">{k.name}</p>
                      <p className="text-[10px] font-mono text-slate-600">
                        {k.key_prefix ? `${k.key_prefix}…` : '—'} · created {timeAgo(k.created_at)}
                        {k.last_used_at ? ` · last used ${timeAgo(k.last_used_at)}` : ' · never used'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className={`text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border ${
                      revoked
                        ? 'bg-slate-800/40 text-slate-500 border-slate-700/40'
                        : 'bg-emerald-950/30 text-emerald-400 border-emerald-900/50'
                    }`}>
                      {revoked ? 'revoked' : 'active'}
                    </span>
                    {!revoked && (
                      <button
                        onClick={() => handleRevoke(k.id, k.name)}
                        disabled={revoking === k.id}
                        className="flex items-center gap-1 text-[10px] font-medium text-slate-500 hover:text-red-400 border border-[#1c2530] hover:border-red-900/50 px-2 py-1 rounded transition-colors disabled:opacity-50"
                      >
                        {revoking === k.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                        Revoke
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Section>

      {/* Firewall blocks */}
      <Section
        title="Firewall blocks"
        desc="IPs currently blocked by containment actions. Unblocking takes effect immediately."
      >
        {blocksLoading ? (
          <div className="flex items-center gap-2 text-xs text-slate-500 py-4">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading blocks…
          </div>
        ) : blocks.length === 0 ? (
          <div className="flex items-center gap-2 text-[11px] text-slate-600 py-3">
            <Shield className="w-4 h-4 text-emerald-500" /> No active blocks.
          </div>
        ) : (
          <div className="divide-y divide-[#141b26] border border-[#1c2530] rounded-md overflow-hidden">
            {blocks.map((b: any, idx: number) => {
              const ip = b.ip || b.ip_address || `#${idx}`;
              return (
                <div key={idx} className="flex items-center justify-between gap-3 px-4 py-3 bg-[#090c11]">
                  <div className="min-w-0">
                    <p className="text-xs font-mono text-red-300">{ip}</p>
                    {b.reason && <p className="text-[10px] text-slate-500 truncate mt-0.5">{b.reason}</p>}
                  </div>
                  <button
                    onClick={() => handleUnblock(ip)}
                    disabled={unblocking === ip}
                    className="text-[10px] font-medium text-slate-400 hover:text-emerald-300 border border-[#1c2530] hover:border-emerald-900/50 px-2.5 py-1.5 rounded transition-colors disabled:opacity-50 flex-shrink-0"
                  >
                    {unblocking === ip ? 'Unblocking…' : 'Unblock'}
                  </button>
                </div>
              );
            })}
          </div>
        )}
        <button
          onClick={loadBlocks}
          className="mt-3 flex items-center gap-1.5 text-[10px] font-medium text-slate-500 hover:text-slate-300 transition-colors"
        >
          <RefreshCw className="w-3 h-3" /> Refresh list
        </button>
      </Section>

      {/* Appearance */}
      <Section
        title="Appearance"
        desc="Console theme. Stored locally in this browser."
      >
        <div className="grid grid-cols-3 gap-2 max-w-md">
          {[
            { mode: 'dark' as const, label: 'Dark', icon: Moon },
            { mode: 'light' as const, label: 'Light', icon: Sun },
            { mode: 'system' as const, label: 'System', icon: Monitor },
          ].map((t) => {
            const Icon = t.icon;
            const selected = themeMode === t.mode;
            return (
              <button
                key={t.mode}
                onClick={() => setThemeMode(t.mode)}
                className={`flex items-center justify-center gap-2 px-3 py-2.5 rounded-md border text-xs font-medium transition-colors ${
                  selected
                    ? 'bg-sky-950/30 border-sky-800/50 text-sky-300'
                    : 'bg-[#090c11] border-[#1c2530] text-slate-400 hover:text-slate-200 hover:border-[#243041]'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {t.label}
              </button>
            );
          })}
        </div>
      </Section>

      {/* Honesty note */}
      <div className="flex items-start gap-2 px-1">
        <AlertTriangle className="w-3.5 h-3.5 text-slate-600 flex-shrink-0 mt-0.5" />
        <p className="text-[10px] text-slate-600 leading-relaxed">
          Threat-intelligence feed integrations are not built yet — when they ship, their configuration will live here.
          Nothing on this page simulates or fabricates data.
        </p>
      </div>
    </div>
  );
}
