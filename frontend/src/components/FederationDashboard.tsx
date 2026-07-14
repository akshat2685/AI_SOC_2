import React, { useState, useEffect } from 'react';
import { Network, ShieldCheck, Activity, Database, Server, RefreshCw } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, AreaChart, Area } from 'recharts';

const CustomLossTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-slate-950/95 border border-red-500/40 backdrop-blur-md p-3 rounded-xl shadow-2xl">
        <p className="text-xs font-bold text-slate-300">Sync Time: {label}</p>
        <div className="flex items-center gap-2 mt-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse"></span>
          <p className="text-xs font-semibold text-white">
            <span className="text-slate-400">Local Loss: </span>
            {payload[0].value.toFixed(4)}
          </p>
        </div>
        <p className="text-[10px] text-slate-500 mt-1 font-medium">Model optimization convergence metric</p>
      </div>
    );
  }
  return null;
};

const CustomAccuracyTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-slate-950/95 border border-indigo-500/40 backdrop-blur-md p-3 rounded-xl shadow-2xl">
        <p className="text-xs font-bold text-slate-300">Sync Time: {label}</p>
        <div className="flex items-center gap-2 mt-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 animate-pulse"></span>
          <p className="text-xs font-semibold text-white">
            <span className="text-slate-400">Global Accuracy: </span>
            {payload[0].value.toFixed(2)}%
          </p>
        </div>
        <p className="text-[10px] text-slate-500 mt-1 font-medium">Privacy-preserving global classification rate</p>
      </div>
    );
  }
  return null;
};

export default function FederationDashboard() {
  const [syncHistory, setSyncHistory] = useState<any[]>([]);

  useEffect(() => {
    // Mocking FedAvg history data
    const data = Array.from({ length: 10 }).map((_, i) => ({
      time: new Date(Date.now() - (10 - i) * 60000).toLocaleTimeString(),
      local_loss: Math.max(0.1, 0.8 - (i * 0.05) + (Math.random() * 0.1)),
      global_accuracy: 85 + (i * 0.5) + (Math.random() * 2),
      peers_active: 3 + Math.floor(Math.random() * 2)
    }));
    setSyncHistory(data);
  }, []);

  return (
    <div className="p-6 h-[calc(100vh-4rem)] overflow-y-auto space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Network className="w-6 h-6 text-indigo-400" />
            Federated Learning Mesh
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Privacy-preserving FedAvg synchronization across decentralized EDYSOR-X instances.
          </p>
        </div>
        <button className="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-2">
          <RefreshCw className="w-4 h-4" />
          Force Global Sync
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: 'Mesh Status', value: 'ACTIVE', icon: Activity, color: 'text-emerald-400' },
          { label: 'Connected Peers', value: '4 / 5', icon: Server, color: 'text-blue-400' },
          { label: 'Global Accuracy', value: '92.4%', icon: ShieldCheck, color: 'text-indigo-400' },
          { label: 'Data Shared', value: '0 Bytes', icon: Database, color: 'text-amber-400', desc: '(Only weights shared, Zero Trust)' },
        ].map((stat, idx) => {
          const Icon = stat.icon;
          return (
            <div key={idx} className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg">
              <div className="flex items-center gap-3 mb-2">
                <div className={`p-2 rounded bg-slate-950 border border-slate-800 ${stat.color}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{stat.label}</span>
              </div>
              <p className={`text-2xl font-bold ${stat.color}`}>{stat.value}</p>
              {stat.desc && <p className="text-[9px] text-slate-500 mt-1">{stat.desc}</p>}
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg h-80">
          <h3 className="text-sm font-bold text-slate-300 mb-4 uppercase tracking-wider">Local Model Loss</h3>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={syncHistory} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="colorLoss" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="time" tick={{fill: '#64748b', fontSize: 10}} />
              <YAxis tick={{fill: '#64748b', fontSize: 10}} />
              <Tooltip content={<CustomLossTooltip />} />
              <Area type="monotone" dataKey="local_loss" stroke="#ef4444" fillOpacity={1} fill="url(#colorLoss)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg h-80">
          <h3 className="text-sm font-bold text-slate-300 mb-4 uppercase tracking-wider">Global Accuracy Trend</h3>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={syncHistory} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="time" tick={{fill: '#64748b', fontSize: 10}} />
              <YAxis domain={['auto', 'auto']} tick={{fill: '#64748b', fontSize: 10}} />
              <Tooltip content={<CustomAccuracyTooltip />} />
              <Line type="monotone" dataKey="global_accuracy" stroke="#8b5cf6" strokeWidth={3} dot={{ fill: '#8b5cf6', strokeWidth: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
