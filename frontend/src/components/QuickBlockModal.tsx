'use client';

import React, { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { 
  X, 
  ShieldAlert, 
  Lock, 
  Clock, 
  Shield, 
  Check, 
  Loader2, 
  AlertTriangle 
} from 'lucide-react';

interface QuickBlockModalProps {
  isOpen: boolean;
  onClose: () => void;
  ipAddress: string;
  initialReason?: string;
  onSuccess?: () => void;
}

export default function QuickBlockModal({
  isOpen,
  onClose,
  ipAddress,
  initialReason = 'Suspicious activity detected',
  onSuccess
}: QuickBlockModalProps) {
  const [blockType, setBlockType] = useState<'temporary' | 'permanent'>('temporary');
  const [hours, setHours] = useState<string>('24h');
  const [reason, setReason] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [success, setSuccess] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      const reset = () => {
        setSuccess(false);
        setError(null);
        setBlockType('temporary');
        setHours('24h');
        setReason(initialReason);
      };
      Promise.resolve().then(reset);
    }
  }, [isOpen, initialReason]);

  if (!isOpen) return null;

  const handleBlock = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.blockIp({
        ip: ipAddress,
        type: blockType,
        hours: blockType === 'temporary' ? hours : undefined,
        reason: reason || 'Manual firewall intervention'
      });
      setSuccess(true);
      if (onSuccess) {
        onSuccess();
      }
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : 'Failed to apply firewall rule';
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm"
        onClick={onClose}
      />
      
      {/* Modal Container */}
      <div className="relative w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
        {/* Banner strip */}
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-red-500 via-orange-500 to-red-600"></div>
        
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-rose-500" /> Quick Block IP Address
          </h3>
          <button 
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-all p-1 rounded-lg hover:bg-slate-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4">
          {success ? (
            <div className="text-center py-6 space-y-3">
              <div className="w-12 h-12 bg-emerald-950/40 border border-emerald-500/30 rounded-full flex items-center justify-center mx-auto text-emerald-400 animate-bounce">
                <Check className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-bold text-slate-200">IP Block Successfully Applied</h4>
              <p className="text-xs text-slate-400 leading-relaxed max-w-xs mx-auto">
                The source IP <span className="font-mono text-emerald-400 font-bold bg-emerald-950/30 px-1.5 py-0.5 rounded border border-emerald-900/30">{ipAddress}</span> has been blocked. Incoming traffic is now dropped at the gateway layer.
              </p>
              <div className="pt-4">
                <button
                  onClick={onClose}
                  className="bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold px-6 py-2 rounded-lg text-xs transition-all"
                >
                  Close Panel
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* Target IP Info */}
              <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 flex items-center gap-3">
                <div className="p-2.5 bg-red-950/40 border border-red-800/30 text-red-400 rounded-xl">
                  <Lock className="w-4 h-4" />
                </div>
                <div>
                  <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Target IP Address</span>
                  <p className="font-mono text-sm font-bold text-white select-all">{ipAddress}</p>
                </div>
              </div>

              {/* Block Duration Options */}
              <div className="space-y-2">
                <label className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Block Type / Duration</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setBlockType('temporary')}
                    className={`p-3 rounded-xl border text-xs font-semibold text-center transition-all flex flex-col items-center justify-center gap-1 ${
                      blockType === 'temporary'
                        ? 'bg-orange-500/10 border-orange-500/50 text-orange-400'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                    }`}
                  >
                    <Clock className="w-4 h-4" />
                    <span>Temporary Block</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setBlockType('permanent')}
                    className={`p-3 rounded-xl border text-xs font-semibold text-center transition-all flex flex-col items-center justify-center gap-1 ${
                      blockType === 'permanent'
                        ? 'bg-red-500/10 border-red-500/50 text-red-400'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                    }`}
                  >
                    <Shield className="w-4 h-4" />
                    <span>Permanent Ban</span>
                  </button>
                </div>
              </div>

              {/* Temporary block options */}
              {blockType === 'temporary' && (
                <div className="space-y-1.5 animate-in fade-in duration-150">
                  <label className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Expiraton Window</label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { label: '1 Hour', value: '1h' },
                      { label: '12 Hours', value: '12h' },
                      { label: '24 Hours', value: '24h' }
                    ].map(opt => (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => setHours(opt.value)}
                        className={`py-2 px-1 rounded-lg border text-[11px] font-bold text-center transition-all ${
                          hours === opt.value
                            ? 'bg-slate-800 border-orange-500/40 text-orange-400'
                            : 'bg-slate-950/50 border-slate-800 text-slate-400 hover:bg-slate-800/30'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Block Reason */}
              <div className="space-y-1.5">
                <label className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Enforcement Reason</label>
                <input
                  type="text"
                  value={reason}
                  onChange={e => setReason(e.target.value)}
                  placeholder="Enter custom enforcement reason..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-red-500/50 placeholder:text-slate-600"
                />
              </div>

              {/* Warning Notice */}
              <div className="bg-red-950/20 border border-red-900/20 rounded-xl p-3 flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                <p className="text-[10px] text-red-400/90 leading-normal">
                  <strong>Warning:</strong> Applying this rule will dynamically push policy rules to the virtual SIEM & VPC routing filters, blacklisting inbound packets immediately.
                </p>
              </div>

              {error && (
                <div className="bg-red-950/40 border border-red-800/80 text-red-400 text-[10px] px-3.5 py-2.5 rounded-xl">
                  {error}
                </div>
              )}

              {/* Action Footer */}
              <div className="pt-2 flex gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="flex-1 bg-slate-950 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 text-slate-300 font-semibold py-2.5 rounded-xl text-xs transition-all"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleBlock}
                  disabled={loading}
                  className="flex-1 bg-gradient-to-r from-red-600 to-red-500 hover:from-red-500 hover:to-red-400 disabled:opacity-50 text-white font-semibold py-2.5 rounded-xl text-xs transition-all flex items-center justify-center gap-1.5 shadow-lg shadow-red-900/10 active:scale-[0.98]"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Applying rule...
                    </>
                  ) : (
                    <>
                      <Lock className="w-3.5 h-3.5" />
                      {blockType === 'temporary' ? 'Apply Temp Block' : 'Apply Permanent Ban'}
                    </>
                  )}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
