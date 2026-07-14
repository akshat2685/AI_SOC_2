'use client';

import React, { useState } from 'react';
import { useStore } from '@/store/useStore';
import { api } from '@/lib/api';
import { 
  ShieldAlert, 
  CreditCard, 
  Lock, 
  Check, 
  Sparkles, 
  Cpu, 
  ArrowRight,
  ShieldCheck,
  RefreshCw
} from 'lucide-react';

interface SaaSPaymentWallProps {
  onSuccess?: () => void;
  inline?: boolean;
}

export default function SaaSPaymentWall({ onSuccess, inline = false }: SaaSPaymentWallProps) {
  const { user, setPremium } = useStore();
  const [selectedPlan, setSelectedPlan] = useState<'pro' | 'enterprise'>('pro');
  const [cardNumber, setCardNumber] = useState('');
  const [cardExpiry, setCardExpiry] = useState('');
  const [cardCvc, setCardCvc] = useState('');
  const [cardName, setCardName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const plans = {
    pro: {
      name: 'Professional SOC',
      price: '$199',
      period: 'user / month',
      badge: 'Most Popular',
      features: [
        'Interactive Cyber Digital Twin Simulations',
        'MITRE ATT&CK Mapping & Attack Graph visualizers',
        'Federated Multi-Tenant threat mapping',
        'Unlimited AI Triage co-pilot chats',
        'Standard SOAR containment playbooks'
      ]
    },
    enterprise: {
      name: 'Enterprise AI SOC',
      price: '$999',
      period: 'org / month',
      badge: 'Best Value',
      features: [
        'All Professional Tier features',
        'Specialized Security Foundation Model integration',
        'Autonomous Detection Engineering (Auto-YARA/Sigma)',
        'Full Executive Business Risk Analytics',
        'SOC 2 & ISO 27001 automated compliance mapping',
        'Dedicated secure agent instance queues'
      ]
    }
  };

  // Card formatting helpers
  const handleCardNumberChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    let value = e.target.value.replace(/\D/g, '');
    value = value.substring(0, 16);
    const matches = value.match(/\d{4,16}/g);
    const match = (matches && matches[0]) || '';
    const parts = [];

    for (let i = 0, len = match.length; i < len; i += 4) {
      parts.push(match.substring(i, i + 4));
    }

    if (parts.length > 0) {
      setCardNumber(parts.join(' '));
    } else {
      setCardNumber(value);
    }
  };

  const handleExpiryChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    let value = e.target.value.replace(/\D/g, '');
    value = value.substring(0, 4);
    if (value.length >= 3) {
      setCardExpiry(`${value.substring(0, 2)}/${value.substring(2, 4)}`);
    } else {
      setCardExpiry(value);
    }
  };

  const handleCvcChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.replace(/\D/g, '');
    setCardCvc(value.substring(0, 4));
  };

  const handleCheckout = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;
    
    setError('');
    setLoading(true);

    try {
      const planDetails = plans[selectedPlan];
      const res = await api.checkout(user.username, planDetails.name, {
        cardNumber: cardNumber.replace(/\s/g, ''),
        cardExpiry,
        cardCvc
      });

      if (res.success) {
        setPremium(true);
        setSuccessMsg(`Perfect! You have been upgraded to the ${planDetails.name}.`);
        if (onSuccess) onSuccess();
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Payment processing failed. Please check details.';
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  if (successMsg) {
    return (
      <div className="bg-slate-900/60 border border-emerald-800/50 rounded-2xl p-8 max-w-lg mx-auto text-center space-y-6 shadow-2xl backdrop-blur-xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-emerald-500"></div>
        <div className="w-16 h-16 bg-emerald-950 border border-emerald-500 rounded-full flex items-center justify-center mx-auto text-emerald-400 shadow-lg shadow-emerald-500/10">
          <ShieldCheck className="w-9 h-9" />
        </div>
        <div className="space-y-2">
          <h3 className="text-xl font-bold text-slate-100">Upgrade Successful!</h3>
          <p className="text-sm text-slate-400 max-w-sm mx-auto">{successMsg}</p>
        </div>
        <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl text-xs text-slate-300 text-left space-y-2">
          <div className="font-semibold text-slate-200">What happens next?</div>
          <p>• Advanced Cyber Digital Twin and Scenario propagators are unlocked.</p>
          <p>• MITRE ATT&CK framework mapping endpoints are activated.</p>
          <p>• Multi-Tenant workspace and Executive dashboards are now accessible.</p>
        </div>
        <button
          onClick={() => window.location.reload()}
          className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold py-2.5 px-4 rounded-xl text-xs transition-all flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/10"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Initialize Premium Operations
        </button>
      </div>
    );
  }

  return (
    <div className={`w-full max-w-5xl mx-auto ${inline ? '' : 'py-8 px-4'} space-y-8`}>
      
      {/* Visual Header */}
      {!inline && (
        <div className="text-center space-y-3 max-w-2xl mx-auto">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 bg-indigo-500/10 border border-indigo-500/20 rounded-full text-xs font-semibold text-indigo-400">
            <Sparkles className="w-3.5 h-3.5" /> Premium Cybersecurity Suite
          </div>
          <h2 className="text-3xl font-extrabold tracking-tight text-slate-100">
            Unlock Advanced SOC Capabilities
          </h2>
          <p className="text-slate-400 text-sm">
            Upgrade your plan to activate real-time cyber digital twins, attack tree propagators, federated indicators correlation, and executive risk telemetry reporting.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        
        {/* Plans selector column */}
        <div className="lg:col-span-7 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            
            {/* Professional Card */}
            <div 
              onClick={() => setSelectedPlan('pro')}
              className={`border rounded-2xl p-5 cursor-pointer transition-all relative ${
                selectedPlan === 'pro' 
                  ? 'bg-indigo-950/20 border-indigo-500 shadow-xl shadow-indigo-500/5' 
                  : 'bg-slate-900/40 border-slate-800/80 hover:border-slate-700/80'
              }`}
            >
              {selectedPlan === 'pro' && (
                <div className="absolute top-3 right-3 bg-indigo-500 text-[9px] font-bold tracking-wider uppercase px-2 py-0.5 rounded text-white">
                  {plans.pro.badge}
                </div>
              )}
              <h3 className="font-bold text-slate-200 text-sm">{plans.pro.name}</h3>
              <div className="mt-2 flex items-baseline gap-1 text-slate-100">
                <span className="text-2xl font-extrabold">{plans.pro.price}</span>
                <span className="text-xs text-slate-400">/ {plans.pro.period}</span>
              </div>
              <p className="text-xs text-slate-400 mt-2">Comprehensive suite for cyber security analysts and medium SOC scale operations.</p>
            </div>

            {/* Enterprise Card */}
            <div 
              onClick={() => setSelectedPlan('enterprise')}
              className={`border rounded-2xl p-5 cursor-pointer transition-all relative ${
                selectedPlan === 'enterprise' 
                  ? 'bg-purple-950/20 border-purple-500 shadow-xl shadow-purple-500/5' 
                  : 'bg-slate-900/40 border-slate-800/80 hover:border-slate-700/80'
              }`}
            >
              {selectedPlan === 'enterprise' && (
                <div className="absolute top-3 right-3 bg-purple-500 text-[9px] font-bold tracking-wider uppercase px-2 py-0.5 rounded text-white">
                  {plans.enterprise.badge}
                </div>
              )}
              <h3 className="font-bold text-slate-200 text-sm">{plans.enterprise.name}</h3>
              <div className="mt-2 flex items-baseline gap-1 text-slate-100">
                <span className="text-2xl font-extrabold">{plans.enterprise.price}</span>
                <span className="text-xs text-slate-400">/ {plans.enterprise.period}</span>
              </div>
              <p className="text-xs text-slate-400 mt-2">Maximum capabilities including compliant models and autonomous defense rules compilation.</p>
            </div>

          </div>

          {/* Premium Features List */}
          <div className="bg-slate-900/30 border border-slate-850 rounded-2xl p-6 space-y-4">
            <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
              <Cpu className="w-4 h-4 text-indigo-500" /> Included in {plans[selectedPlan].name}
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {plans[selectedPlan].features.map((feat, idx) => (
                <div key={idx} className="flex items-start gap-2.5 text-xs text-slate-300">
                  <span className="mt-0.5 w-4 h-4 rounded bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 flex-shrink-0">
                    <Check className="w-2.5 h-2.5" />
                  </span>
                  <span>{feat}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Payments column */}
        <div className="lg:col-span-5">
          <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 shadow-xl relative overflow-hidden backdrop-blur-xl">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 to-indigo-500"></div>
            
            <h3 className="text-sm font-bold text-slate-200 mb-6 flex items-center gap-2">
              <CreditCard className="w-4.5 h-4.5 text-blue-500" /> Secure Payment Checkout
            </h3>

            {/* Glossy Credit Card Preview */}
            <div className="relative h-40 w-full bg-gradient-to-br from-indigo-700 via-blue-800 to-indigo-900 rounded-xl p-5 text-white shadow-lg shadow-indigo-900/30 mb-6 overflow-hidden flex flex-col justify-between">
              <div className="absolute top-0 right-0 w-32 h-32 bg-white/5 rounded-full blur-2xl -mr-8 -mt-8"></div>
              <div className="absolute bottom-0 left-0 w-24 h-24 bg-black/10 rounded-full blur-xl -ml-8 -mb-8"></div>
              
              <div className="flex justify-between items-start">
                <div className="space-y-1">
                  <div className="text-[10px] uppercase font-bold tracking-widest text-indigo-200">ShieldAI Security Premium</div>
                  <div className="text-xs font-semibold text-white/90">Cardholder Access</div>
                </div>
                <div className="w-10 h-7 bg-white/10 border border-white/20 rounded-md flex items-center justify-center text-xs font-extrabold italic tracking-wider text-white/80">
                  VISA
                </div>
              </div>

              <div className="font-mono text-lg tracking-widest my-2 select-all">
                {cardNumber || '•••• •••• •••• ••••'}
              </div>

              <div className="flex justify-between items-end">
                <div>
                  <div className="text-[8px] uppercase tracking-wider text-indigo-200/80">Card Member</div>
                  <div className="font-semibold text-xs truncate max-w-[160px]">
                    {cardName ? cardName.toUpperCase() : 'MEMBER ANALYST'}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[8px] uppercase tracking-wider text-indigo-200/80">Expires</div>
                  <div className="font-semibold text-xs font-mono">{cardExpiry || 'MM/YY'}</div>
                </div>
              </div>
            </div>

            {/* Actual payment input form */}
            <form onSubmit={handleCheckout} className="space-y-4">
              {error && (
                <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-3 rounded-lg text-xs flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Cardholder Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. John Doe"
                  value={cardName}
                  onChange={e => setCardName(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-850 rounded-lg px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-blue-500 transition-all placeholder:text-slate-600"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Card Number</label>
                <input
                  type="text"
                  required
                  placeholder="4111 2222 3333 4444"
                  value={cardNumber}
                  onChange={handleCardNumberChange}
                  className="w-full bg-slate-950 border border-slate-850 rounded-lg px-3 py-2 text-xs text-slate-100 font-mono focus:outline-none focus:border-blue-500 transition-all placeholder:text-slate-600"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Expiration</label>
                  <input
                    type="text"
                    required
                    placeholder="MM/YY"
                    value={cardExpiry}
                    onChange={handleExpiryChange}
                    className="w-full bg-slate-950 border border-slate-850 rounded-lg px-3 py-2 text-xs text-slate-100 font-mono focus:outline-none focus:border-blue-500 transition-all placeholder:text-slate-600"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">CVC / CVV</label>
                  <input
                    type="password"
                    required
                    placeholder="•••"
                    value={cardCvc}
                    onChange={handleCvcChange}
                    className="w-full bg-slate-950 border border-slate-850 rounded-lg px-3 py-2 text-xs text-slate-100 font-mono focus:outline-none focus:border-blue-500 transition-all placeholder:text-slate-600"
                  />
                </div>
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold py-3 px-4 rounded-xl text-xs transition-all flex items-center justify-center gap-1.5 shadow-lg shadow-blue-500/10 active:scale-[0.99]"
                >
                  {loading ? (
                    <>
                      <Lock className="w-3.5 h-3.5 animate-pulse" /> Processing Secure Payment...
                    </>
                  ) : (
                    <>
                      Pay {plans[selectedPlan].price} & Upgrade to {plans[selectedPlan].name} <ArrowRight className="w-3.5 h-3.5" />
                    </>
                  )}
                </button>
              </div>

              <p className="text-[10px] text-slate-500 text-center">
                💳 Secure 256-bit SSL encrypted checkout. Payments processed via simulated Stripe secure gateway.
              </p>
            </form>
          </div>
        </div>

      </div>
    </div>
  );
}
