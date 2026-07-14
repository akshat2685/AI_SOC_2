'use client';

import React from 'react';
import dynamic from 'next/dynamic';
import { useStore } from '@/store/useStore';
import DashboardShell from '@/components/DashboardShell';
import DashboardView from '@/components/DashboardView';
import IncidentsView from '@/components/IncidentsView';
import MemoryExplorerView from '@/components/MemoryExplorerView';
import ExecutiveDashboardView from '@/components/ExecutiveDashboardView';
import ReportingView from '@/components/ReportingView';
import SettingsView from '@/components/SettingsView';
import FederationDashboard from '@/components/FederationDashboard';
import ChaosDashboard from '@/components/ChaosDashboard';
import SaaSPaymentWall from '@/components/SaaSPaymentWall';

const AttackGraphView = dynamic(() => import('@/components/AttackGraphView'), {
  ssr: false,
});

export default function Home() {
  const { activePage, user } = useStore();
  
  const isPremium = user?.premium === true;

  const renderActiveView = () => {
    // Gate premium pages
    const premiumPages = ['graph', 'executive', 'federation', 'chaos'];
    if (premiumPages.includes(activePage) && !isPremium) {
      return (
        <div className="py-12 bg-zinc-950/20 rounded-3xl border border-slate-900/40 p-6">
          <SaaSPaymentWall />
        </div>
      );
    }

    switch (activePage) {
      case 'dashboard':
        return <DashboardView />;
      case 'incidents':
        return <IncidentsView />;
      case 'graph':
        return <AttackGraphView />;
      case 'memory':
        return <MemoryExplorerView />;
      case 'executive':
        return <ExecutiveDashboardView />;
      case 'federation':
        return <FederationDashboard />;
      case 'chaos':
        return <ChaosDashboard />;
      case 'reporting':
        return <ReportingView />;
      case 'threat-intel':
        return <ReportingView />;
      case 'settings':
        return <SettingsView />;
      default:
        return <DashboardView />;
    }
  };

  return (
    <DashboardShell>
      {renderActiveView()}
    </DashboardShell>
  );
}
