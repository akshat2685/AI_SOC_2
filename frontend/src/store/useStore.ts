import { create } from 'zustand';

export type ActivePage = 'dashboard' | 'incidents' | 'graph' | 'memory' | 'executive' | 'reporting' | 'threat-intel' | 'settings' | 'federation' | 'chaos';

export interface User {
  username: string;
  role: string;
  tenant_id: string;
  token: string;
  premium?: boolean;
}

export interface Incident {
  id: number;
  timestamp: string;
  title: string;
  severity: string;
  status: string;
  correlation_key: string;
  llm_summary?: string;
  verdict: string;
  analyst_notes?: string;
  resolved_at?: string;
  tenant_id: string;
}

export interface Alert {
  id: number;
  timestamp: string;
  title: string;
  severity: string;
  confidence: string;
  confidence_score: number;
  attack_type: string;
  evidence: string;
  attacker_ip: string;
  verdict: string;
  incident_id?: number;
  tenant_id: string;
}

export interface ThreatIntelConfig {
  alienVaultEnabled: boolean;
  alienVaultApiKey: string;
  abuseChEnabled: boolean;
  mispEnabled: boolean;
  mispUrl: string;
  mispApiKey: string;
}

export interface SecurityConfig {
  sessionTimeout: number; // minutes
  autoLogoutEnabled: boolean;
}

export interface WebhookConfig {
  slackWebhookUrl: string;
  slackEnabled: boolean;
  teamsWebhookUrl: string;
  teamsEnabled: boolean;
}

interface StoreState {
  user: User | null;
  currentTenant: string;
  activePage: ActivePage;
  incidents: Incident[];
  alerts: Alert[];
  sidebarOpen: boolean;
  theme: 'dark' | 'light';
  themeMode: 'dark' | 'light' | 'system';
  wsMessages: any[];
  
  // Custom configurations
  threatIntelConfig: ThreatIntelConfig;
  securityConfig: SecurityConfig;
  webhookConfig: WebhookConfig;
  
  setAuth: (user: User | null) => void;
  setPremium: (premium: boolean) => void;
  setCurrentTenant: (tenant: string) => void;
  setActivePage: (page: ActivePage) => void;
  setIncidents: (incidents: Incident[]) => void;
  setAlerts: (alerts: Alert[]) => void;
  toggleSidebar: () => void;
  setThemeMode: (mode: 'dark' | 'light' | 'system') => void;
  updateThreatIntelConfig: (config: Partial<ThreatIntelConfig>) => void;
  updateSecurityConfig: (config: Partial<SecurityConfig>) => void;
  updateWebhookConfig: (config: Partial<WebhookConfig>) => void;
  addWsMessage: (msg: any) => void;
  logout: () => void;
}

// Helpers for localStorage persistence
const safeGet = (key: string, fallback: any) => {
  if (typeof window === 'undefined') return fallback;
  try {
    const val = localStorage.getItem(key);
    return val ? JSON.parse(val) : fallback;
  } catch {
    return fallback;
  }
};

const safeSet = (key: string, val: any) => {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(key, JSON.stringify(val));
  } catch (e) {
    console.error('localStorage set failed:', e);
  }
};

const resolveTheme = (mode: 'dark' | 'light' | 'system'): 'dark' | 'light' => {
  if (mode === 'system') {
    if (typeof window !== 'undefined') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return 'dark';
  }
  return mode;
};

export const useStore = create<StoreState>((set) => {
  const initialThemeMode = safeGet('themeMode', 'dark');
  const initialThreatIntel = safeGet('threatIntelConfig', {
    alienVaultEnabled: false,
    alienVaultApiKey: '',
    abuseChEnabled: true,
    mispEnabled: false,
    mispUrl: '',
    mispApiKey: ''
  });
  const initialSecurity = safeGet('securityConfig', {
    sessionTimeout: 15,
    autoLogoutEnabled: false
  });
  const initialWebhook = safeGet('webhookConfig', {
    slackWebhookUrl: '',
    slackEnabled: false,
    teamsWebhookUrl: '',
    teamsEnabled: false
  });

  return {
    user: null,
    currentTenant: 'default',
    activePage: 'dashboard',
    incidents: [],
    alerts: [],
    sidebarOpen: true,
    themeMode: initialThemeMode,
    theme: resolveTheme(initialThemeMode),
    threatIntelConfig: initialThreatIntel,
    securityConfig: initialSecurity,
    webhookConfig: initialWebhook,
    wsMessages: [],

    setAuth: (user) => set({ user, currentTenant: user ? user.tenant_id : 'default' }),
    setPremium: (premium) => set((state) => ({ user: state.user ? { ...state.user, premium } : null })),
    setCurrentTenant: (currentTenant) => set({ currentTenant }),
    setActivePage: (activePage) => set({ activePage }),
    setIncidents: (incidents) => set({ incidents }),
    setAlerts: (alerts) => set({ alerts }),
    toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
    setThemeMode: (themeMode) => set(() => {
      safeSet('themeMode', themeMode);
      const theme = resolveTheme(themeMode);
      
      // Sync DOM class
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
      
      return { themeMode, theme };
    }),
    updateThreatIntelConfig: (config) => set((state) => {
      const updated = { ...state.threatIntelConfig, ...config };
      safeSet('threatIntelConfig', updated);
      return { threatIntelConfig: updated };
    }),
    updateSecurityConfig: (config) => set((state) => {
      const updated = { ...state.securityConfig, ...config };
      safeSet('securityConfig', updated);
      return { securityConfig: updated };
    }),
    updateWebhookConfig: (config) => set((state) => {
      const updated = { ...state.webhookConfig, ...config };
      safeSet('webhookConfig', updated);
      return { webhookConfig: updated };
    }),
    addWsMessage: (msg) => set((state) => ({ wsMessages: [msg, ...state.wsMessages].slice(0, 50) })),
    logout: () => set({ user: null, activePage: 'dashboard', incidents: [], alerts: [], wsMessages: [] }),
  };
});
