import React from 'react';
import { Brain, Network, Activity, HelpCircle } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

interface XAIPanelProps {
  xaiData?: {
    confidence: number;
    decision_map: string;
    feature_attributions: Record<string, number>;
    counterfactuals: string[];
    alternative_hypotheses: string[];
  };
}

const CustomSHAPTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const val = payload[0].value;
    const isRisk = val > 0;
    return (
      <div className={`bg-slate-950/95 border ${isRisk ? 'border-red-500/40' : 'border-emerald-500/40'} backdrop-blur-md p-3 rounded-xl shadow-2xl`}>
        <p className="text-xs font-bold text-slate-200 capitalize">{payload[0].payload.name}</p>
        <div className="flex items-center gap-2 mt-1.5">
          <span className={`w-2.5 h-2.5 rounded-full ${isRisk ? 'bg-red-500' : 'bg-emerald-500'}`}></span>
          <p className="text-xs font-semibold text-white">
            <span className="text-slate-400">SHAP Weight: </span>
            {isRisk ? `+${val.toFixed(3)}` : val.toFixed(3)}
          </p>
        </div>
        <p className="text-[10px] text-slate-500 mt-1 font-medium">
          {isRisk ? 'Increases anomaly risk level' : 'Decreases anomaly risk level'}
        </p>
      </div>
    );
  }
  return null;
};

export default function XAIPanel({ xaiData }: XAIPanelProps) {
  if (!xaiData) return null;

  // Transform SHAP values for Recharts
  const shapData = Object.entries(xaiData.feature_attributions || {}).map(([key, value]) => ({
    name: key.replace(/_/g, ' '),
    value: value
  })).sort((a, b) => Math.abs(b.value) - Math.abs(a.value));

  return (
    <div className="bg-slate-900 border border-indigo-500/30 rounded-xl overflow-hidden shadow-2xl">
      <div className="bg-indigo-950/50 p-4 border-b border-indigo-500/30 flex items-center gap-3">
        <Brain className="text-indigo-400 w-5 h-5" />
        <h3 className="font-bold text-indigo-300">Explainable AI (XAI) Engine</h3>
      </div>
      
      <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* SHAP Feature Attributions */}
        <div>
          <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
            <Activity className="w-4 h-4 text-emerald-400" />
            Decision Weights (SHAP)
          </h4>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={shapData} layout="vertical" margin={{ top: 0, right: 0, left: 40, bottom: 0 }}>
                <XAxis type="number" hide />
                <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{fill: '#94a3b8', fontSize: 10}} />
                <Tooltip 
                  cursor={{fill: '#1e293b'}} 
                  content={<CustomSHAPTooltip />}
                />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {shapData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.value > 0 ? '#ef4444' : '#22c55e'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[10px] text-slate-500 mt-2">Red indicates factors increasing risk score; Green indicates mitigating factors.</p>
        </div>

        {/* Counterfactuals & Hypotheses */}
        <div className="space-y-4">
          <div>
            <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2 flex items-center gap-2">
              <Network className="w-4 h-4 text-blue-400" />
              Counterfactual Analysis
            </h4>
            <ul className="space-y-2">
              {xaiData.counterfactuals?.map((cf, idx) => (
                <li key={idx} className="text-sm text-slate-300 bg-slate-800/50 p-2 rounded border border-slate-700/50 flex gap-2 items-start">
                  <span className="text-blue-400 font-mono mt-0.5">&gt;</span> {cf}
                </li>
              ))}
            </ul>
          </div>
          
          <div>
            <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2 flex items-center gap-2">
              <HelpCircle className="w-4 h-4 text-amber-400" />
              Alternative Hypotheses
            </h4>
            <ul className="space-y-2">
              {xaiData.alternative_hypotheses?.map((ah, idx) => (
                <li key={idx} className="text-sm text-slate-300 bg-slate-800/50 p-2 rounded border border-slate-700/50 flex gap-2 items-start">
                  <span className="text-amber-400 font-mono mt-0.5">?</span> {ah}
                </li>
              ))}
            </ul>
          </div>
        </div>
        
      </div>
    </div>
  );
}
