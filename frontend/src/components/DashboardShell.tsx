'use client';

import React, { useEffect, useState } from 'react';
import { useStore, ActivePage } from '@/store/useStore';
import { api } from '@/lib/api';
import CopilotDrawer from '@/components/CopilotDrawer';
import { 
  Shield, 
  LayoutDashboard, 
  AlertTriangle, 
  Settings, 
  LogOut, 
  User as UserIcon, 
  Globe, 
  ScrollText,
  Menu, 
  X,
  Radio,
  Bell,
  Sparkles,
  ShieldCheck,
  Rocket,
  Plug,
  MonitorSmartphone,
  Swords
} from 'lucide-react';

interface ShellProps {
  children: React.ReactNode;
}

export default function DashboardShell({ children }: ShellProps) {
  const { 
    user, 
    setAuth, 
    activePage, 
    setActivePage, 
    currentTenant, 
    sidebarOpen, 
    toggleSidebar,
    addWsMessage,
    theme,
    securityConfig,
    logout
  } = useStore();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);
  const [loginError, setLoginError] = useState('');
  const [loading, setLoading] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [notifications, setNotifications] = useState<any[]>([]);

  // Sync theme class to document element
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const root = document.documentElement;
      if (theme === 'light') {
        root.classList.add('light');
        root.classList.remove('dark');
      } else {
        root.classList.add('dark');
        root.classList.remove('light');
      }
    }
  }, [theme]);

  // Analyst Account Inactivity Session Timeout
  useEffect(() => {
    if (!user || !securityConfig.autoLogoutEnabled) return;

    let timeoutId: any;
    const resetTimer = () => {
      if (timeoutId) clearTimeout(timeoutId);
      
      const ms = securityConfig.sessionTimeout * 60 * 1000;
      timeoutId = setTimeout(() => {
        log.warning(`Inactivity timeout reached: automatically logging out analyst.`);
        logout();
      }, ms);
    };

    const events = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'];
    events.forEach(name => window.addEventListener(name, resetTimer));
    
    // Start initial timer
    resetTimer();

    return () => {
      if (timeoutId) clearTimeout(timeoutId);
      events.forEach(name => window.removeEventListener(name, resetTimer));
    };
  }, [user, securityConfig.autoLogoutEnabled, securityConfig.sessionTimeout, logout]);

  // WebSocket Connection
  useEffect(() => {
    if (!user) return;

    let ws: WebSocket;
    const connectWs = () => {
      try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          setWsConnected(true);
          log.info('WebSocket Connected');
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            addWsMessage(data);
            
            // Show inline toast notification
            setNotifications(prev => [data, ...prev].slice(0, 5));
          } catch (e) {
            log.warning('WS parse error:', e);
          }
        };

        ws.onclose = () => {
          setWsConnected(false);
          // Try to reconnect in 5 seconds
          setTimeout(connectWs, 5000);
        };

        ws.onerror = () => {
          setWsConnected(false);
        };
      } catch (err) {
        log.warning('WS creation error:', err);
      }
    };

    connectWs();
    return () => {
      if (ws) ws.close();
    };
  }, [user, addWsMessage]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError('');
    setLoading(true);
    try {
      if (isRegistering) {
        // Register flow — the identity is stored as the user's email.
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(username.trim())) {
          setLoginError('Please enter a valid email address.');
          return;
        }
        const regRes = await api.register(username, password);
        // After successful registration, auto-login
        const res = await api.login(username, password);
        setAuth({
          username: res.username,
          role: res.role,
          tenant_id: res.tenant_id || 'default',
          token: res.token,
          premium: res.premium
        });
      } else {
        // Login flow
        const res = await api.login(username, password);
        setAuth({
          username: res.username,
          role: res.role,
          tenant_id: res.tenant_id || 'default',
          token: res.token,
          premium: res.premium
        });
      }
      // Post-login landing: SOC Command Center once onboarding is complete.
      // The onboarding wizard (built separately) sets localStorage 'edysor_onboarded'='true'
      // on completion. Until then, keep the legacy dashboard landing.
      try {
        if (typeof window !== 'undefined' && window.localStorage.getItem('edysor_onboarded') === 'true') {
          setActivePage('soc');
        }
      } catch {
        /* localStorage unavailable — stay on default landing */
      }
    } catch (err: any) {
      setLoginError(err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  };

  // Login / Register View
  if (!user) {
    return (
      <div className="min-h-screen bg-[#090c11] text-slate-200 flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-[#0e1319] border border-[#1c2530] p-8 rounded-lg">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-10 h-10 bg-[#131a23] border border-[#243041] rounded-md flex items-center justify-center">
              <Shield className="w-5 h-5 text-sky-400" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white leading-none">
                EDYSOR <span className="text-slate-500 font-semibold">AI-SOC</span>
              </h1>
              <p className="text-[11px] text-slate-500 mt-1">Autonomous Detection &amp; Response</p>
            </div>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-[10px] font-semibold text-slate-500 uppercase tracking-[0.14em] mb-2">Email</label>
              <input
                type="email"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="you@company.com"
                autoComplete="email"
                className="w-full bg-[#090c11] border border-[#1c2530] rounded-md px-3.5 py-2.5 text-sm focus:outline-none focus:border-sky-500/70 text-slate-100 placeholder:text-slate-600"
                required
              />
            </div>
            <div>
              <label className="block text-[10px] font-semibold text-slate-500 uppercase tracking-[0.14em] mb-2">Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder={isRegistering ? 'Choose a strong password' : 'Enter your password'}
                autoComplete={isRegistering ? 'new-password' : 'current-password'}
                className="w-full bg-[#090c11] border border-[#1c2530] rounded-md px-3.5 py-2.5 text-sm focus:outline-none focus:border-sky-500/70 text-slate-100 placeholder:text-slate-600"
                required
              />
            </div>

            {loginError && (
              <div className="text-xs bg-red-950/30 border border-red-900/60 text-red-400 px-3.5 py-2.5 rounded-md">
                {loginError}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-sky-600 hover:bg-sky-500 text-white text-sm font-semibold py-2.5 rounded-md transition-colors disabled:opacity-50"
            >
              {loading ? 'Authenticating...' : (isRegistering ? 'Create Account & Sign In' : 'Sign In')}
            </button>

            <div className="text-center pt-2">
              <button
                type="button"
                onClick={() => {
                  setIsRegistering(!isRegistering);
                  setLoginError('');
                }}
                className="text-xs text-sky-400 hover:text-sky-300 font-medium focus:outline-none"
              >
                {isRegistering ? 'Already have an account? Sign In' : "Don't have an account? Register Now"}
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  const NAV_GROUPS = [
    {
      label: 'Operate',
      items: [
        { id: 'soc', label: 'Command Center', icon: Shield },
        { id: 'twin', label: 'Digital Twin', icon: Swords },
        { id: 'dashboard', label: 'Overview', icon: LayoutDashboard },
        { id: 'endpoints', label: 'Endpoints', icon: MonitorSmartphone },
        { id: 'incidents', label: 'Incidents', icon: AlertTriangle },
        { id: 'approvals', label: 'Response', icon: ShieldCheck },
      ],
    },
    {
      label: 'Manage',
      items: [
        { id: 'integrations', label: 'Integrations', icon: Plug },
        { id: 'onboarding', label: 'Onboarding', icon: Rocket },
        { id: 'reporting', label: 'Audit Log', icon: ScrollText },
        { id: 'settings', label: 'Settings', icon: Settings },
      ],
    },
  ];
  const navItems = NAV_GROUPS.flatMap(g => g.items);

  return (
    <div className="min-h-screen bg-[#090c11] text-slate-200 flex overflow-hidden">
      
      {/* Real-time alert notifications overlay */}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full">
        {notifications.map((notif, idx) => (
          <div 
            key={idx} 
            className="bg-[#0e1319] border border-[#1c2530] p-4 rounded-md flex gap-3 animate-slide-in relative overflow-hidden"
          >
            <div className="absolute top-0 left-0 h-full w-1 bg-red-500"></div>
            <div className="w-8 h-8 rounded-md bg-red-950/30 border border-red-900/50 flex items-center justify-center text-red-400 flex-shrink-0">
              <AlertTriangle className="w-4 h-4" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-bold text-slate-200 truncate">{notif.event_type || 'New Ingested Log'}</p>
              <p className="text-[11px] text-slate-400 truncate">{notif.endpoint || notif.source_ip || 'Details matching baseline rules'}</p>
            </div>
            <button 
              onClick={() => setNotifications(prev => prev.filter((_, i) => i !== idx))}
              className="text-slate-500 hover:text-slate-300"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>

      {/* Sidebar Navigation */}
      <aside className={`bg-[#0b0f15] border-r border-[#1a2230] w-64 flex-shrink-0 flex flex-col transition-all duration-300 ${sidebarOpen ? 'ml-0' : '-ml-64'}`}>
        <div className="h-16 px-5 border-b border-[#1a2230] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-[#131a23] border border-[#243041] rounded-md flex items-center justify-center">
              <Shield className="w-4 h-4 text-sky-400" />
            </div>
            <span className="font-bold text-[13px] tracking-tight text-white">EDYSOR <span className="text-slate-500 font-semibold">AI-SOC</span></span>
          </div>
          <button onClick={toggleSidebar} className="lg:hidden text-slate-500 hover:text-slate-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tenant: read-only — the backend scopes all data to the signed-in tenant */}
        <div className="px-5 py-3.5 border-b border-[#1a2230]">
          <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-[0.14em] mb-1">Tenant</p>
          <p className="text-xs font-mono text-slate-300 truncate">{currentTenant || 'default'}</p>
        </div>

        <nav className="flex-1 py-4 px-3 space-y-4 overflow-y-auto">
          {NAV_GROUPS.map(group => (
            <div key={group.label}>
              <p className="px-3 mb-1.5 text-[10px] font-semibold text-slate-600 uppercase tracking-[0.14em]">{group.label}</p>
              <div className="space-y-0.5">
                {group.items.map(item => {
                  const Icon = item.icon;
                  const active = activePage === item.id;
                  return (
                    <button
                      key={item.id}
                      onClick={() => setActivePage(item.id as ActivePage)}
                      className={`relative w-full flex items-center gap-3 px-3 py-2 rounded-md text-[13px] font-medium transition-colors ${
                        active
                          ? 'bg-[#141c27] text-white'
                          : 'text-slate-400 hover:bg-[#111722] hover:text-slate-200'
                      }`}
                    >
                      {active && <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 bg-sky-400 rounded-full" />}
                      <Icon className={`w-4 h-4 ${active ? 'text-sky-400' : 'text-slate-500'}`} />
                      {item.label}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* User Info / Logout */}
        <div className="p-4 border-t border-[#1a2230] flex flex-col gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-md bg-[#131a23] border border-[#243041] flex items-center justify-center text-slate-400">
              <UserIcon className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-slate-200 truncate">{user.username}</p>
              <div className="flex flex-wrap gap-1.5 items-center">
                <span className="text-[10px] text-slate-500 uppercase tracking-[0.12em]">{user.role}</span>
                {user.premium && (
                  <span className="inline-flex items-center gap-0.5 text-[9px] font-semibold text-amber-400/90 border border-amber-900/50 px-1.5 py-0.5 rounded uppercase tracking-wider">
                    <Sparkles className="w-2.5 h-2.5" /> Premium
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={() => useStore.getState().logout()}
            className="w-full flex items-center justify-center gap-2 text-slate-500 hover:text-red-400 border border-[#1c2530] hover:border-red-900/50 rounded-md py-2 text-xs font-medium transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" /> Log Out
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top Navbar */}
        <header className="h-14 border-b border-[#1a2230] bg-[#0b0f15] flex items-center justify-between px-6 z-10 flex-shrink-0">
          <div className="flex items-center gap-4">
            {!sidebarOpen && (
              <button onClick={toggleSidebar} className="text-slate-500 hover:text-slate-200">
                <Menu className="w-5 h-5" />
              </button>
            )}
            <h2 className="text-[13px] font-semibold text-slate-200 tracking-wide">
              {navItems.find(n => n.id === activePage)?.label || 'System'}
            </h2>
          </div>

          <div className="flex items-center gap-3">
            {/* Live Feed WebSocket indicator */}
            <div className="flex items-center gap-2">
              <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-emerald-400 animate-pulse' : 'bg-red-500'}`} />
              <span className="text-[10px] font-mono uppercase tracking-[0.14em] text-slate-500">
                {wsConnected ? 'Live' : 'Offline'}
              </span>
            </div>
          </div>
        </header>

        {/* Dynamic page content */}
        <main className="flex-1 overflow-y-auto bg-[#090c11] relative">
          {children}
          <CopilotDrawer />
        </main>
      </div>
    </div>
  );
}

// Simple client-side logger dummy to prevent build errors
const log = {
  info: (msg: string, ...args: any[]) => console.log(`[INFO] ${msg}`, ...args),
  warning: (msg: string, ...args: any[]) => console.warn(`[WARN] ${msg}`, ...args),
  error: (msg: string, ...args: any[]) => console.error(`[ERROR] ${msg}`, ...args)
};
