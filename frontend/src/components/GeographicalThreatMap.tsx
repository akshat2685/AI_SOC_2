'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useStore } from '@/store/useStore';
import { Globe, ShieldAlert, Crosshair, Map, ShieldCheck, Zap } from 'lucide-react';
import QuickBlockModal from './QuickBlockModal';

interface GeoLocation {
  country: string;
  city: string;
  lat: number;
  lng: number;
}

// Deterministic IP to Geo mapper
function getGeoFromIP(ip: string): GeoLocation {
  let hash = 0;
  for (let i = 0; i < ip.length; i++) {
    hash = ip.charCodeAt(i) + ((hash << 5) - hash);
  }
  hash = Math.abs(hash);
  
  const locations = [
    { country: 'United States', city: 'San Jose, CA', lat: 37.33, lng: -121.89 },
    { country: 'China', city: 'Beijing', lat: 39.90, lng: 116.40 },
    { country: 'Russia', city: 'St. Petersburg', lat: 59.93, lng: 30.33 },
    { country: 'Germany', city: 'Munich', lat: 48.13, lng: 11.58 },
    { country: 'Brazil', city: 'São Paulo', lat: -23.55, lng: -46.63 },
    { country: 'Netherlands', city: 'Amsterdam', lat: 52.36, lng: 4.90 },
    { country: 'Ukraine', city: 'Kyiv', lat: 50.45, lng: 30.52 },
    { country: 'North Korea', city: 'Pyongyang', lat: 39.03, lng: 125.76 },
    { country: 'Iran', city: 'Tehran', lat: 35.68, lng: 51.38 },
    { country: 'United Kingdom', city: 'London', lat: 51.50, lng: -0.12 }
  ];
  
  return locations[hash % locations.length];
}

// Overlapping circles modeling continental landmasses for the canvas dots
const landmassCircles = [
  // North America
  { lng: -100, lat: 45, r: 25 },
  { lng: -115, lat: 55, r: 20 },
  { lng: -80, lat: 40, r: 15 },
  { lng: -105, lat: 32, r: 12 },
  { lng: -120, lat: 60, r: 12 },
  { lng: -40, lat: 72, r: 12 }, // Greenland
  // South America
  { lng: -60, lat: -15, r: 18 },
  { lng: -65, lat: -5, r: 15 },
  { lng: -60, lat: -35, r: 12 },
  { lng: -70, lat: -45, r: 8 },
  // Europe
  { lng: 15, lat: 50, r: 12 },
  { lng: 30, lat: 60, r: 12 },
  { lng: 5, lat: 45, r: 8 },
  // Africa
  { lng: 25, lat: 10, r: 20 },
  { lng: 15, lat: 5, r: 18 },
  { lng: 22, lat: -15, r: 12 },
  { lng: 28, lat: -28, r: 8 },
  // Asia
  { lng: 100, lat: 50, r: 25 },
  { lng: 80, lat: 45, r: 20 },
  { lng: 115, lat: 35, r: 18 },
  { lng: 75, lat: 30, r: 15 },
  { lng: 105, lat: 22, r: 12 },
  { lng: 125, lat: 55, r: 12 },
  { lng: 135, lat: 45, r: 10 },
  { lng: 50, lat: 32, r: 10 },
  { lng: 75, lat: 15, r: 10 },
  // Australia
  { lng: 135, lat: -25, r: 12 },
  { lng: 145, lat: -30, r: 8 }
];

function isGlobalLand(lng: number, lat: number): boolean {
  for (const circle of landmassCircles) {
    const dLng = lng - circle.lng;
    const dLat = lat - circle.lat;
    // Simple Euclidean distance test
    if (Math.sqrt(dLng * dLng + dLat * dLat) <= circle.r) {
      return true;
    }
  }
  return false;
}

export default function GeographicalThreatMap() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { alerts, theme } = useStore();
  const [hoveredAlert, setHoveredAlert] = useState<any | null>(null);
  const [blockingIp, setBlockingIp] = useState<string | null>(null);
  const [blockReason, setBlockReason] = useState('');

  // Target center (EDYSOR Local SOC Hub is situated at San Jose, California: 37.33, -121.89)
  const socHub = { lat: 37.33, lng: -121.89 };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationId: number;
    let pulseAngle = 0;
    let particleOffset = 0;

    // Convert Geo-coordinates (Lon/Lat) to Canvas X/Y using Equirectangular projection
    const getXY = (lng: number, lat: number, w: number, h: number) => {
      // Scale longitude [-180, 180] to [0, w]
      const x = ((lng + 180) / 360) * w;
      // Scale latitude [-90, 90] to [0, h] with inversed Y axis
      const y = ((90 - lat) / 180) * h;
      return { x, y };
    };

    const drawMap = () => {
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      // Define Theme colors
      const isLight = theme === 'light';
      const bgColor = isLight ? '#ffffff' : '#090d16';
      const gridColor = isLight ? 'rgba(15, 23, 42, 0.05)' : 'rgba(255, 255, 255, 0.04)';
      const landColor = isLight ? '#cbd5e1' : '#1e293b';
      const socHubColor = '#3b82f6';
      const attackColor = '#ef4444';

      // Draw outer background
      ctx.fillStyle = bgColor;
      ctx.fillRect(0, 0, w, h);

      // Draw Grid lines
      ctx.strokeStyle = gridColor;
      ctx.lineWidth = 1;
      
      // Vertical meridians
      for (let x = 0; x < w; x += w / 18) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      // Horizontal parallels
      for (let y = 0; y < h; y += h / 10) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      // Render dotted world landmasses
      ctx.fillStyle = landColor;
      const stepLng = 5;
      const stepLat = 5;
      for (let lng = -180; lng <= 180; lng += stepLng) {
        for (let lat = -60; lat <= 80; lat += stepLat) {
          if (isGlobalLand(lng, lat)) {
            const { x, y } = getXY(lng, lat, w, h);
            ctx.beginPath();
            ctx.arc(x, y, 1.5, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }

      // Filter alerts with valid attacker IP addresses
      const activeAlerts = alerts
        .filter(a => a.attacker_ip && a.attacker_ip.includes('.'))
        .slice(0, 8); // Display top 8 current alerts to keep visual clean

      const hubXY = getXY(socHub.lng, socHub.lat, w, h);

      // Draw Local SOC Target Hub
      ctx.beginPath();
      ctx.arc(hubXY.x, hubXY.y, 6 + Math.sin(pulseAngle) * 2, 0, Math.PI * 2);
      ctx.fillStyle = socHubColor;
      ctx.fill();
      
      ctx.beginPath();
      ctx.arc(hubXY.x, hubXY.y, 14 + Math.sin(pulseAngle) * 4, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(59, 130, 246, ${0.4 - Math.sin(pulseAngle) * 0.1})`;
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Render each threat vector
      activeAlerts.forEach((alert, idx) => {
        const geo = getGeoFromIP(alert.attacker_ip);
        const startXY = getXY(geo.lng, geo.lat, w, h);

        const isCritical = alert.severity === 'CRITICAL';
        const threatColor = isCritical ? '#ef4444' : '#f59e0b';

        // 1. Plot attacking node
        ctx.beginPath();
        const baseRadius = isCritical ? 5 : 4;
        const animatedPulse = baseRadius + Math.sin(pulseAngle + idx) * 1.5;
        ctx.arc(startXY.x, startXY.y, animatedPulse, 0, Math.PI * 2);
        ctx.fillStyle = threatColor;
        ctx.fill();

        // Pulsating shockwave
        ctx.beginPath();
        const shockRadius = 12 + Math.sin(pulseAngle + idx * 0.5) * 6;
        ctx.arc(startXY.x, startXY.y, shockRadius, 0, Math.PI * 2);
        ctx.strokeStyle = isCritical ? `rgba(239, 68, 68, ${0.35 - (shockRadius - 12)/12})` : `rgba(245, 158, 11, ${0.35 - (shockRadius - 12)/12})`;
        ctx.lineWidth = 1.2;
        ctx.stroke();

        // 2. Draw curved attack vector trace
        ctx.beginPath();
        ctx.moveTo(startXY.x, startXY.y);
        
        // Control point for quadratic curve to create elegant arching missiles
        const midX = (startXY.x + hubXY.x) / 2;
        const midY = (startXY.y + hubXY.y) / 2 - 40; // arch height offset
        
        ctx.quadraticCurveTo(midX, midY, hubXY.x, hubXY.y);
        ctx.strokeStyle = isCritical ? 'rgba(239, 68, 68, 0.25)' : 'rgba(245, 158, 11, 0.22)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // 3. Draw animated flying tracer particle
        const t = (particleOffset + idx * 0.25) % 1;
        // Calculate point on quadratic curve
        const px = (1 - t) * (1 - t) * startXY.x + 2 * (1 - t) * t * midX + t * t * hubXY.x;
        const py = (1 - t) * (1 - t) * startXY.y + 2 * (1 - t) * t * midY + t * t * hubXY.y;

        ctx.beginPath();
        ctx.arc(px, py, 2.5, 0, Math.PI * 2);
        ctx.fillStyle = threatColor;
        ctx.fill();

        // Tiny tracer tail
        ctx.shadowColor = threatColor;
        ctx.shadowBlur = 6;
        ctx.beginPath();
        ctx.arc(px, py, 1.2, 0, Math.PI * 2);
        ctx.fillStyle = '#ffffff';
        ctx.fill();
        ctx.shadowBlur = 0; // reset
      });

      // Render custom HUD coordinates overlays
      ctx.font = '9px "Space Mono", monospace';
      ctx.fillStyle = isLight ? '#475569' : '#64748b';
      ctx.fillText(`CENTER SOC HUB: ${socHub.lat.toFixed(2)}N, ${Math.abs(socHub.lng).toFixed(2)}W`, 15, h - 15);
      ctx.fillText(`THREAT SCALE: ${activeAlerts.length} TRACKED VECTORS`, w - 180, h - 15);

      pulseAngle += 0.04;
      particleOffset += 0.006;
      animationId = requestAnimationFrame(drawMap);
    };

    drawMap();

    return () => {
      cancelAnimationFrame(animationId);
    };
  }, [alerts, theme]);

  const activeAlerts = alerts
    .filter(a => a.attacker_ip && a.attacker_ip.includes('.'))
    .slice(0, 5);

  return (
    <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
            <Globe className="w-4 h-4 text-rose-500 animate-pulse" /> Global Incident Origin Heatmap
          </h3>
          <p className="text-xs text-slate-400 mt-1">Live equirectangular coordinates projection mapping incoming attacker origin IPs dynamically to local tenant SOC nodes.</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1 bg-red-950/40 text-red-400 border border-red-900/30 px-2 py-0.5 rounded-full text-[9px] font-bold">
            <ShieldAlert className="w-2.5 h-2.5 animate-pulse" /> {alerts.length} Ingress Feeds
          </span>
          <span className="inline-flex items-center gap-1 bg-blue-950/40 text-blue-400 border border-blue-900/30 px-2 py-0.5 rounded-full text-[9px] font-bold">
            <ShieldCheck className="w-2.5 h-2.5" /> SOC Protected
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 items-stretch">
        {/* Dynamic Threat Canvas */}
        <div className="lg:col-span-2 relative h-[300px] border border-slate-850 bg-slate-950 rounded-xl overflow-hidden shadow-inner flex items-center justify-center">
          <canvas
            ref={canvasRef}
            width={800}
            height={300}
            className="w-full h-full object-cover select-none"
          />
          <div className="absolute top-3 left-3 bg-slate-900/90 border border-slate-800 backdrop-blur-sm px-2.5 py-1.5 rounded-lg text-[9px] text-slate-400 font-mono flex items-center gap-1.5 shadow">
            <Crosshair className="w-3 h-3 text-red-500 animate-spin" /> Live Radar Active
          </div>
          <div className="absolute top-3 right-3 bg-slate-900/90 border border-slate-800 backdrop-blur-sm px-2.5 py-1.5 rounded-lg text-[9px] text-slate-400 font-mono shadow">
            Hub: <span className="text-blue-400 font-bold">San Jose, CA</span>
          </div>
        </div>

        {/* Threat Origin IP Side Panel Feed */}
        <div className="border border-slate-850 rounded-xl p-4 flex flex-col justify-between bg-slate-950/20">
          <div className="space-y-3">
            <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5 border-b border-slate-850 pb-2">
              <Zap className="w-3.5 h-3.5 text-amber-500" /> Origin IP Telemetry
            </h4>

            {activeAlerts.length === 0 ? (
              <div className="text-center text-xs text-slate-500 py-12">
                No active external threat vectors mapped.
              </div>
            ) : (
              <div className="space-y-2.5 max-h-[200px] overflow-y-auto pr-1">
                {activeAlerts.map((alert) => {
                  const geo = getGeoFromIP(alert.attacker_ip);
                  const isCritical = alert.severity === 'CRITICAL';
                  
                  return (
                    <div
                      key={alert.id}
                      onMouseEnter={() => setHoveredAlert(alert)}
                      onMouseLeave={() => setHoveredAlert(null)}
                      className="bg-slate-950/60 hover:bg-slate-900/40 border border-slate-850 p-2.5 rounded-lg flex items-center justify-between gap-3 transition-all cursor-default"
                    >
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setBlockingIp(alert.attacker_ip);
                              setBlockReason(`Geo-IP Block: ${alert.title} originating from ${geo.city}, ${geo.country}`);
                            }}
                            className="font-mono text-[10px] font-bold text-rose-400 hover:text-rose-300 hover:underline bg-rose-950/30 px-1.5 py-0.5 rounded border border-rose-900/30 transition-all cursor-pointer"
                            title="Click to Block IP"
                          >
                            {alert.attacker_ip}
                          </button>
                          <span className={`text-[8px] font-bold uppercase px-1 rounded-sm ${isCritical ? 'bg-red-950/50 text-red-400 border border-red-900/30' : 'bg-amber-950/50 text-amber-400 border border-amber-900/30'}`}>
                            {alert.severity}
                          </span>
                        </div>
                        <p className="text-[10px] text-slate-300 truncate font-semibold">
                          {geo.city}, {geo.country}
                        </p>
                      </div>
                      <div className="text-right text-[9px] text-slate-500 font-medium">
                        Mapped
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="border-t border-slate-850 pt-3 text-center text-[9px] text-slate-500 italic">
            Click IP nodes to invoke dynamic gateway firewall rule containment.
          </div>
        </div>
      </div>

      <QuickBlockModal
        isOpen={blockingIp !== null}
        onClose={() => setBlockingIp(null)}
        ipAddress={blockingIp || ''}
        initialReason={blockReason}
      />
    </div>
  );
}
