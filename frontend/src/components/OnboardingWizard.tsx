'use client';

import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useStore, ActivePage } from '@/store/useStore';
import IntegrationConnectModal, { Connector, Integration, backendUrlForSnippet } from '@/components/IntegrationConnectModal';
import {
  Rocket,
  Laptop,
  Server,
  Cloud,
  KeyRound,
  ShieldCheck,
  Activity,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  XCircle,
  Loader2,
  Copy,
  Check,
  Plug,
  ChevronRight,
  Building2,
  SlidersHorizontal,
} from 'lucide-react';

const STEPS = [
  { n: 1, title: 'Organization', desc: 'Tell us about your organization' },
  { n: 2, title: 'Endpoints', desc: 'Connect Windows, macOS & Linux agents' },
  { n: 3, title: 'Security Tools', desc: 'Connect SIEM, EDR & firewalls' },
  { n: 4, title: 'Identity', desc: 'Connect your identity provider' },
  { n: 5, title: 'Cloud', desc: 'Connect cloud environments' },
  { n: 6, title: 'Response', desc: 'Set your autonomy level' },
  { n: 7, title: 'Health Check', desc: 'Verify every connection' },
  { n: 8, title: 'Start Monitoring', desc: 'Review and go live' },
];

const CATEGORY_KEYWORDS: Record<string, string[]> = {
  tools: ['siem', 'edr', 'firewall', 'threat', 'network', 'vulnerability', 'ids', 'ips'],
  identity: ['identity', 'iam', 'sso', 'directory', 'okta', 'entra', 'ldap'],
  cloud: ['cloud', 'aws', 'azure', 'gcp', 'kubernetes'],
};

interface Agent {
  device_id: string;
  hostname: string;
  platform: string;
  os_version?: string;
  agent_version?: string;
  status?: string;
  last_heartbeat_at?: string;
}

interface HealthResult {
  integrationId: string | number;
  name: string;
  ok: boolean;
  checks: { name: string; passed: boolean; detail?: string }[];
  error?: string;
}

const OS_PLATFORMS = [
  { key: 'windows', label: 'Windows', icon: Laptop, shell: 'powershell' },
  { key: 'macos', label: 'macOS', icon: Laptop, shell: 'bash' },
  { key: 'linux', label: 'Linux', icon: Server, shell: 'bash' },
] as const;

function installSnippet(platform: string): string {
  const base = backendUrlForSnippet();
  if (platform === 'windows') {
    return [
      '$env:EDYSOR_URL="' + base + '"',
      '$env:EDYSOR_API_KEY="<paste-api-key>"  # Settings -> API Keys (sent as X-API-Key header)',
      '',
      '# Register this device via the live /agents/register endpoint.',
      '# The Windows telemetry sensor ships in a later release.',
      'Invoke-RestMethod -Method Post `',
      '  -Uri "$env:EDYSOR_URL/api/v1/agents/register" `',
      '  -Headers @{"X-API-Key"=$env:EDYSOR_API_KEY} `',
      '  -ContentType "application/json" `',
      '  -Body (@{hostname=$env:COMPUTERNAME; platform="windows"; `',
      '    os_version=(Get-CimInstance Win32_OperatingSystem).Version; `',
      '    arch=$env:PROCESSOR_ARCHITECTURE; agent_version="0.1.0"} | ConvertTo-Json)',
    ].join('\n');
  }
  // Linux/macOS: the real reference sensor (sensor/edysor_sensor.py).
  return [
    '# EDYSOR sensor — review before running.',
    'set -e',
    'mkdir -p ~/.local/share/edysor-sensor && cd ~/.local/share/edysor-sensor',
    'curl -fsSL -O https://raw.githubusercontent.com/akshat2685/AI_SOC_2/mvp-live/sensor/edysor_sensor.py',
    'curl -fsSL -O https://raw.githubusercontent.com/akshat2685/AI_SOC_2/mvp-live/sensor/requirements.txt',
    'python3 -m pip install -r requirements.txt',
    '',
    '# 1. Create an API key in the product: Settings -> API Keys.',
    '#    The sensor sends it in the X-API-Key header.',
    '# 2. Write ~/.config/edysor/sensor.json (chmod 600):',
    '#      {"backend_url": "' + base + '", "api_key": "<paste-api-key>", "interval_seconds": 30}',
    '# 3. Test:  python3 edysor_sensor.py --once',
    '# 4. Run:   nohup python3 edysor_sensor.py >/tmp/edysor-sensor.log 2>&1 &',
    '# First run registers the device and prints its device_id.',
  ].join('\n');
}

function loadLocal(key: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  return window.localStorage.getItem(key) ?? fallback;
}

export default function OnboardingWizard() {
  const { setActivePage } = useStore();
  const [step, setStep] = useState(1);
  const [completed, setCompleted] = useState<number[]>([]);
  const [skipped, setSkipped] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [backendNote, setBackendNote] = useState('');

  const [catalog, setCatalog] = useState<Connector[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [modalConnector, setModalConnector] = useState<Connector | null>(null);

  const [orgName, setOrgName] = useState(() => loadLocal('edysor_org_name', ''));
  const [industry, setIndustry] = useState(() => loadLocal('edysor_org_industry', ''));
  const [orgSize, setOrgSize] = useState(() => loadLocal('edysor_org_size', ''));
  const [autonomy, setAutonomy] = useState(() => loadLocal('edysor_autonomy_level', 'assisted'));

  const [healthResults, setHealthResults] = useState<HealthResult[] | null>(null);
  const [healthRunning, setHealthRunning] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  // Manual agent registration form state, per platform
  const [regHost, setRegHost] = useState<Record<string, string>>({});
  const [regOs, setRegOs] = useState<Record<string, string>>({});
  const [regResult, setRegResult] = useState<Record<string, Agent | null>>({});
  const [regLoading, setRegLoading] = useState<Record<string, boolean>>({});
  const [regError, setRegError] = useState<Record<string, string>>({});

  useEffect(() => {
    let active = true;
    (async () => {
      const missing: string[] = [];
      try {
        const s = await api.getOnboardingState();
        if (!active) return;
        setStep(s.current_step || 1);
        setCompleted(s.completed_steps || []);
        setSkipped(s.skipped_steps || []);
      } catch { missing.push('onboarding state'); }
      try {
        const c = await api.getConnectorCatalog();
        if (active) setCatalog(c.connectors || []);
      } catch { missing.push('connector catalog'); }
      try {
        const list = await api.listIntegrations();
        if (active) setIntegrations(list.integrations || []);
      } catch { missing.push('integrations'); }
      try {
        const a = await api.listAgents();
        if (active) setAgents(a.agents || []);
      } catch { missing.push('agents'); }
      if (active) {
        if (missing.length > 0) setBackendNote(`Backend not ready yet for: ${missing.join(', ')}. Progress below is kept on this device until the API is live.`);
        setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  const persist = async (nextStep: number, nextCompleted: number[], nextSkipped: number[]) => {
    setSaving(true);
    try {
      await api.updateOnboardingState({ current_step: nextStep, completed_steps: nextCompleted, skipped_steps: nextSkipped });
    } catch {
      // Backend being built in parallel — keep local progress so the wizard still works
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('edysor_onboarding_local', JSON.stringify({ current_step: nextStep, completed_steps: nextCompleted, skipped_steps: nextSkipped }));
      }
    } finally {
      setSaving(false);
    }
  };

  const goContinue = async () => {
    if (step === 1) {
      window.localStorage.setItem('edysor_org_name', orgName);
      window.localStorage.setItem('edysor_org_industry', industry);
      window.localStorage.setItem('edysor_org_size', orgSize);
    }
    if (step === 6) {
      window.localStorage.setItem('edysor_autonomy_level', autonomy);
    }
    const nextCompleted = completed.includes(step) ? completed : [...completed, step];
    const next = Math.min(step + 1, 8);
    setCompleted(nextCompleted);
    setStep(next);
    await persist(next, nextCompleted, skipped);
  };

  const goSkip = async () => {
    const nextSkipped = skipped.includes(step) ? skipped : [...skipped, step];
    const next = Math.min(step + 1, 8);
    setSkipped(nextSkipped);
    setStep(next);
    await persist(next, completed, nextSkipped);
  };

  const goBack = () => setStep(Math.max(step - 1, 1));

  const refreshIntegrations = async () => {
    try {
      const list = await api.listIntegrations();
      setIntegrations(list.integrations || []);
    } catch { /* keep existing */ }
  };

  const refreshAgents = async () => {
    try {
      const a = await api.listAgents();
      setAgents(a.agents || []);
    } catch { /* keep existing */ }
  };

  const handleManualRegister = async (platform: string) => {
    const hostname = (regHost[platform] || '').trim();
    if (!hostname) {
      setRegError(prev => ({ ...prev, [platform]: 'Hostname is required' }));
      return;
    }
    setRegLoading(prev => ({ ...prev, [platform]: true }));
    setRegError(prev => ({ ...prev, [platform]: '' }));
    try {
      const agent = await api.registerAgent({
        hostname,
        platform,
        os_version: regOs[platform] || undefined,
        arch: 'x86_64',
        agent_version: '0.1.0',
      });
      setRegResult(prev => ({ ...prev, [platform]: agent }));
      await refreshAgents();
    } catch (e) {
      setRegError(prev => ({ ...prev, [platform]: e instanceof Error ? e.message : 'Registration failed' }));
    } finally {
      setRegLoading(prev => ({ ...prev, [platform]: false }));
    }
  };

  const copySnippet = async (platform: string) => {
    try {
      await navigator.clipboard.writeText(installSnippet(platform));
      setCopied(platform);
      setTimeout(() => setCopied(null), 2000);
    } catch { /* clipboard unavailable */ }
  };

  const runHealthCheck = async () => {
    setHealthRunning(true);
    const results: HealthResult[] = [];
    for (const integ of integrations) {
      try {
        const res = await api.testIntegration(integ.id);
        const checks = res.checks || [];
        results.push({
          integrationId: integ.id,
          name: integ.name,
          ok: checks.length > 0 ? checks.every((c: { passed: boolean }) => c.passed) : !!res.ok,
          checks,
        });
      } catch (e) {
        results.push({ integrationId: integ.id, name: integ.name, ok: false, checks: [], error: e instanceof Error ? e.message : 'Test failed' });
      }
    }
    setHealthResults(results);
    setHealthRunning(false);
  };

  const filterCatalog = (group: 'tools' | 'identity' | 'cloud'): Connector[] => {
    const keywords = CATEGORY_KEYWORDS[group];
    const matched = catalog.filter(c => keywords.some(k => (c.category || '').toLowerCase().includes(k)));
    return matched.length > 0 ? matched : catalog;
  };

  const percent = Math.round((completed.length / STEPS.length) * 100);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center text-slate-400 text-sm">
        <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading onboarding…
      </div>
    );
  }

  const stepMeta = STEPS[step - 1];

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-11 h-11 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/20">
          <Rocket className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-slate-100">Set up your SOC</h1>
          <p className="text-xs text-slate-400">Connect your environment — EDYSOR takes it from there.</p>
        </div>
      </div>

      {backendNote && (
        <div className="mb-4 text-xs bg-amber-950/40 border border-amber-800/60 text-amber-300 px-4 py-3 rounded-xl">{backendNote}</div>
      )}

      {/* Progress */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Setup progress</span>
          <span className="text-xs font-bold text-blue-400">{percent}%</span>
        </div>
        <div className="h-2 bg-slate-800 rounded-full overflow-hidden mb-4">
          <div className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 transition-all" style={{ width: `${percent}%` }} />
        </div>
        <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
          {STEPS.map(s => {
            const done = completed.includes(s.n);
            const skip = skipped.includes(s.n);
            const current = s.n === step;
            return (
              <button
                key={s.n}
                onClick={() => setStep(s.n)}
                className={`rounded-lg px-2 py-2 text-center border transition-all ${
                  current ? 'border-blue-500 bg-blue-950/40' : done ? 'border-green-800 bg-green-950/20' : 'border-slate-800 bg-slate-950/40 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-center mb-1">
                  {done ? <CheckCircle2 className="w-4 h-4 text-green-400" /> : skip ? <span className="text-[10px] text-slate-500">skipped</span> : <span className={`text-[11px] font-bold ${current ? 'text-blue-300' : 'text-slate-500'}`}>{s.n}</span>}
                </div>
                <p className={`text-[10px] font-semibold leading-tight ${current ? 'text-blue-200' : 'text-slate-400'}`}>{s.title}</p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Step body */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 mb-6">
        <h2 className="text-base font-bold text-slate-100 mb-1">Step {stepMeta.n}: {stepMeta.title}</h2>
        <p className="text-xs text-slate-400 mb-6">{stepMeta.desc}</p>

        {step === 1 && <OrgStep orgName={orgName} setOrgName={setOrgName} industry={industry} setIndustry={setIndustry} orgSize={orgSize} setOrgSize={setOrgSize} />}

        {step === 2 && (
          <EndpointsStep
            agents={agents}
            regHost={regHost} setRegHost={setRegHost}
            regOs={regOs} setRegOs={setRegOs}
            regResult={regResult} regLoading={regLoading} regError={regError}
            onRegister={handleManualRegister} onCopy={copySnippet} copied={copied}
          />
        )}

        {(step === 3 || step === 4 || step === 5) && (
          <ConnectorPickerStep
            connectors={filterCatalog(step === 3 ? 'tools' : step === 4 ? 'identity' : 'cloud')}
            integrations={integrations}
            onConnect={setModalConnector}
            emptyHint={step === 3 ? 'SIEM, EDR, firewall connectors' : step === 4 ? 'Identity provider connectors' : 'Cloud connectors'}
          />
        )}

        {step === 6 && <ResponseStep autonomy={autonomy} setAutonomy={setAutonomy} />}

        {step === 7 && (
          <HealthStep integrations={integrations} results={healthResults} running={healthRunning} onRun={runHealthCheck} />
        )}

        {step === 8 && (
          <FinishStep
            orgName={orgName}
            integrations={integrations}
            agents={agents}
            autonomy={autonomy}
            completedCount={completed.length}
            onFinish={async () => {
              const nextCompleted = completed.includes(8) ? completed : [...completed, 8];
              setCompleted(nextCompleted);
              await persist(8, nextCompleted, skipped);
              // Mark onboarding complete so the shell lands on the SOC Command Center.
              if (typeof window !== 'undefined') window.localStorage.setItem('edysor_onboarded', 'true');
              setActivePage('soc' as ActivePage);
            }}
          />
        )}
      </div>

      {/* Nav */}
      <div className="flex items-center justify-between">
        <button
          onClick={goBack}
          disabled={step === 1}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold text-slate-300 bg-slate-900 border border-slate-800 hover:bg-slate-800 disabled:opacity-40 transition-all"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <div className="flex items-center gap-3">
          {step < 8 && (
            <button onClick={goSkip} className="text-xs font-semibold text-slate-400 hover:text-slate-200 transition-all">
              Skip for now
            </button>
          )}
          {step < 8 && (
            <button
              onClick={goContinue}
              disabled={saving}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 transition-all"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              Continue <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      <IntegrationConnectModal
        connector={modalConnector}
        onClose={() => setModalConnector(null)}
        onCreated={() => { refreshIntegrations(); }}
      />
    </div>
  );
}

/* ---------------- Step 1: Organization ---------------- */
function OrgStep({ orgName, setOrgName, industry, setIndustry, orgSize, setOrgSize }: {
  orgName: string; setOrgName: (v: string) => void;
  industry: string; setIndustry: (v: string) => void;
  orgSize: string; setOrgSize: (v: string) => void;
}) {
  const inputCls = 'w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-blue-500/80';
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div>
        <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">Organization name</label>
        <input value={orgName} onChange={e => setOrgName(e.target.value)} placeholder="Acme Corp" className={inputCls} />
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">Industry</label>
        <input value={industry} onChange={e => setIndustry(e.target.value)} placeholder="Financial services" className={inputCls} />
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">Organization size</label>
        <select value={orgSize} onChange={e => setOrgSize(e.target.value)} className={inputCls}>
          <option value="">Select…</option>
          <option value="1-50">1–50</option>
          <option value="51-500">51–500</option>
          <option value="501-5000">501–5,000</option>
          <option value="5000+">5,000+</option>
        </select>
      </div>
      <p className="md:col-span-2 text-[11px] text-slate-500 flex items-center gap-1.5">
        <Building2 className="w-3.5 h-3.5" /> Saved on this device until the tenant-profile API is available.
      </p>
    </div>
  );
}

/* ---------------- Step 2: Endpoints ---------------- */
function EndpointsStep({ agents, regHost, setRegHost, regOs, setRegOs, regResult, regLoading, regError, onRegister, onCopy, copied }: {
  agents: Agent[];
  regHost: Record<string, string>; setRegHost: (v: Record<string, string>) => void;
  regOs: Record<string, string>; setRegOs: (v: Record<string, string>) => void;
  regResult: Record<string, Agent | null>;
  regLoading: Record<string, boolean>;
  regError: Record<string, string>;
  onRegister: (platform: string) => void;
  onCopy: (platform: string) => void;
  copied: string | null;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <div className="space-y-4">
      <div className="grid md:grid-cols-3 gap-4">
        {OS_PLATFORMS.map(os => {
          const Icon = os.icon;
          const isOpen = expanded === os.key;
          const result = regResult[os.key];
          return (
            <div key={os.key} className="bg-slate-950/60 border border-slate-800 rounded-xl p-4">
              <div className="flex items-center gap-2.5 mb-3">
                <div className="w-9 h-9 rounded-lg bg-blue-600/15 border border-blue-500/25 flex items-center justify-center">
                  <Icon className="w-5 h-5 text-blue-400" />
                </div>
                <h3 className="text-sm font-bold text-slate-100">{os.label}</h3>
              </div>

              <button
                onClick={() => setExpanded(isOpen ? null : os.key)}
                className="w-full text-left text-xs font-semibold text-blue-400 hover:text-blue-300 mb-2 flex items-center justify-between"
              >
                Download agent / install snippet
                <ChevronRight className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
              </button>
              {isOpen && (
                <div className="mb-3">
                  <div className="relative bg-black/60 border border-slate-800 rounded-lg p-3 mb-2">
                    <pre className="text-[10px] text-slate-300 whitespace-pre-wrap font-mono leading-relaxed">{installSnippet(os.key)}</pre>
                    <button
                      onClick={() => onCopy(os.key)}
                      className="absolute top-2 right-2 text-slate-400 hover:text-white bg-slate-800 rounded-md p-1.5"
                      title="Copy snippet"
                    >
                      {copied === os.key ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                  <p className="text-[10px] text-slate-500">Create an API key under Settings → API Keys and paste it where indicated (sent as <span className="font-mono">X-API-Key</span> header). Linux/macOS installs the real telemetry sensor; Windows registers the device via the live <span className="font-mono">/agents/register</span> endpoint.</p>
                </div>
              )}

              <div className="border-t border-slate-800 pt-3 space-y-2">
                <p className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider">Register manually</p>
                <input
                  placeholder="Hostname (e.g. WIN-ABC123)"
                  value={regHost[os.key] || ''}
                  onChange={e => setRegHost({ ...regHost, [os.key]: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500/80"
                />
                <input
                  placeholder="OS version (optional)"
                  value={regOs[os.key] || ''}
                  onChange={e => setRegOs({ ...regOs, [os.key]: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500/80"
                />
                <button
                  onClick={() => onRegister(os.key)}
                  disabled={!!regLoading[os.key]}
                  className="w-full bg-slate-800 hover:bg-slate-700 text-slate-100 text-xs font-semibold py-2 rounded-lg disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {regLoading[os.key] && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Register device
                </button>
                {regError[os.key] && <p className="text-[11px] text-red-400">{regError[os.key]}</p>}
                {result && (
                  <div className="text-[11px] bg-green-950/30 border border-green-800/50 rounded-lg p-2.5">
                    <p className="text-green-300 font-semibold flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> Registered</p>
                    <p className="text-slate-400 mt-1 font-mono break-all">device_id: {result.device_id}</p>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4">
        <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider mb-3">Registered agents ({agents.length})</h4>
        {agents.length === 0 ? (
          <p className="text-xs text-slate-500">No agents registered yet. Register a device above to see it here.</p>
        ) : (
          <div className="space-y-2">
            {agents.map(a => (
              <div key={a.device_id} className="flex items-center justify-between text-xs bg-slate-900 border border-slate-800 rounded-lg px-3 py-2">
                <div>
                  <p className="font-semibold text-slate-200">{a.hostname}</p>
                  <p className="text-slate-500 font-mono text-[10px]">{a.device_id} · {a.platform}{a.os_version ? ` · ${a.os_version}` : ''}</p>
                </div>
                <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-full ${a.status === 'online' ? 'text-green-400 bg-green-950/40' : 'text-slate-400 bg-slate-800'}`}>
                  {a.status || 'unknown'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- Steps 3-5: Connector picker ---------------- */
function ConnectorPickerStep({ connectors, integrations, onConnect, emptyHint }: {
  connectors: Connector[];
  integrations: Integration[];
  onConnect: (c: Connector) => void;
  emptyHint: string;
}) {
  if (connectors.length === 0) {
    return <p className="text-xs text-slate-500">No {emptyHint} found in the catalog yet.</p>;
  }
  return (
    <div className="grid md:grid-cols-2 gap-4">
      {connectors.map(c => {
        const connected = integrations.some(i => i.connector_key === c.key);
        return (
          <div key={c.key} className="bg-slate-950/60 border border-slate-800 rounded-xl p-4">
            <div className="flex items-start justify-between mb-2">
              <div>
                <h4 className="text-sm font-bold text-slate-100">{c.name}</h4>
                <p className="text-[11px] text-slate-500">{c.category} · {c.connection_method}</p>
              </div>
              {connected && <span className="text-[10px] font-bold uppercase tracking-wider text-green-400 bg-green-950/40 px-2 py-1 rounded-full">Connected</span>}
            </div>
            {c.capabilities?.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-3">
                {c.capabilities.slice(0, 4).map(cap => (
                  <span key={cap} className="text-[10px] bg-slate-800/80 text-slate-300 px-2 py-0.5 rounded-md">{cap}</span>
                ))}
              </div>
            )}
            <button
              onClick={() => onConnect(c)}
              className="w-full text-xs font-semibold py-2 rounded-lg bg-blue-600/20 border border-blue-500/30 text-blue-300 hover:bg-blue-600/30 transition-all flex items-center justify-center gap-2"
            >
              <Plug className="w-3.5 h-3.5" /> {connected ? 'Connect another' : 'Connect'}
            </button>
          </div>
        );
      })}
    </div>
  );
}

/* ---------------- Step 6: Response autonomy ---------------- */
const AUTONOMY_LEVELS = [
  { key: 'advisory', title: 'Advisory', desc: 'AI detects, investigates and recommends. No autonomous response — a human decides everything.' },
  { key: 'assisted', title: 'Assisted', desc: 'AI prepares response actions. A human approves each action before it executes.' },
  { key: 'controlled', title: 'Controlled Autonomous', desc: 'AI may execute explicitly authorized low-risk actions automatically. High-impact actions still need approval.' },
];

function ResponseStep({ autonomy, setAutonomy }: { autonomy: string; setAutonomy: (v: string) => void }) {
  return (
    <div className="space-y-3">
      {AUTONOMY_LEVELS.map(l => {
        const selected = autonomy === l.key;
        return (
          <button
            key={l.key}
            onClick={() => setAutonomy(l.key)}
            className={`w-full text-left rounded-xl border p-4 transition-all ${selected ? 'border-blue-500 bg-blue-950/30' : 'border-slate-800 bg-slate-950/60 hover:border-slate-700'}`}
          >
            <div className="flex items-center gap-3">
              <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${selected ? 'border-blue-400' : 'border-slate-600'}`}>
                {selected && <div className="w-2.5 h-2.5 rounded-full bg-blue-400" />}
              </div>
              <div>
                <p className={`text-sm font-bold ${selected ? 'text-blue-200' : 'text-slate-200'}`}>{l.title}</p>
                <p className="text-xs text-slate-400 mt-0.5">{l.desc}</p>
              </div>
            </div>
          </button>
        );
      })}
      <p className="text-[11px] text-slate-500 flex items-center gap-1.5">
        <SlidersHorizontal className="w-3.5 h-3.5" /> Policy draft — stored locally. Enforcement in the response engine ships in a later release.
      </p>
    </div>
  );
}

/* ---------------- Step 7: Health check ---------------- */
function HealthStep({ integrations, results, running, onRun }: {
  integrations: Integration[];
  results: HealthResult[] | null;
  running: boolean;
  onRun: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-400">{integrations.length} integration{integrations.length === 1 ? '' : 's'} to verify.</p>
        <button
          onClick={onRun}
          disabled={running || integrations.length === 0}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50"
        >
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
          {running ? 'Running…' : 'Run health check'}
        </button>
      </div>

      {integrations.length === 0 && (
        <p className="text-xs text-slate-500">No integrations connected yet — go back and connect at least one, or skip this step.</p>
      )}

      {results && (
        <div className="space-y-3">
          {results.map(r => (
            <div key={String(r.integrationId)} className="bg-slate-950/60 border border-slate-800 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                {r.ok ? <CheckCircle2 className="w-5 h-5 text-green-400" /> : <XCircle className="w-5 h-5 text-red-400" />}
                <p className="text-sm font-bold text-slate-100">{r.name}</p>
                <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${r.ok ? 'text-green-400 bg-green-950/40' : 'text-red-400 bg-red-950/40'}`}>
                  {r.ok ? 'Pass' : 'Fail'}
                </span>
              </div>
              {r.error && <p className="text-xs text-red-400">{r.error}</p>}
              {r.checks.map((c, i) => (
                <div key={i} className="flex items-start gap-2 text-xs ml-7 mb-1">
                  {c.passed ? <CheckCircle2 className="w-3.5 h-3.5 text-green-400 mt-0.5" /> : <XCircle className="w-3.5 h-3.5 text-red-400 mt-0.5" />}
                  <div>
                    <span className="text-slate-300 font-semibold">{c.name}</span>
                    {c.detail && <span className="text-slate-500"> — {c.detail}</span>}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------- Step 8: Finish ---------------- */
function FinishStep({ orgName, integrations, agents, autonomy, completedCount, onFinish }: {
  orgName: string;
  integrations: Integration[];
  agents: Agent[];
  autonomy: string;
  completedCount: number;
  onFinish: () => void;
}) {
  const autonomyLabel = AUTONOMY_LEVELS.find(l => l.key === autonomy)?.title || autonomy;
  const connectedCount = integrations.length;
  return (
    <div className="space-y-4">
      <div className="grid md:grid-cols-3 gap-4">
        <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 text-center">
          <Plug className="w-6 h-6 text-blue-400 mx-auto mb-2" />
          <p className="text-2xl font-bold text-slate-100">{connectedCount}</p>
          <p className="text-[11px] text-slate-400 uppercase tracking-wider">Integrations</p>
        </div>
        <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 text-center">
          <Laptop className="w-6 h-6 text-blue-400 mx-auto mb-2" />
          <p className="text-2xl font-bold text-slate-100">{agents.length}</p>
          <p className="text-[11px] text-slate-400 uppercase tracking-wider">Agents</p>
        </div>
        <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 text-center">
          <ShieldCheck className="w-6 h-6 text-blue-400 mx-auto mb-2" />
          <p className="text-sm font-bold text-slate-100 mt-1">{autonomyLabel}</p>
          <p className="text-[11px] text-slate-400 uppercase tracking-wider mt-1">Autonomy (draft)</p>
        </div>
      </div>
      <p className="text-xs text-slate-400">
        {orgName ? <><span className="font-semibold text-slate-200">{orgName}</span> is </> : 'Your environment is '}
        {completedCount >= 7 ? 'ready' : 'partially configured'} — EDYSOR will now monitor connected sources, triage detections and investigate incidents.
      </p>
      <button
        onClick={onFinish}
        className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold py-3.5 rounded-xl transition-all flex items-center justify-center gap-2"
      >
        <Rocket className="w-4 h-4" /> Go to SOC Command Center
      </button>
    </div>
  );
}
