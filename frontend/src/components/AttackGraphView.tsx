/* eslint-disable @typescript-eslint/no-explicit-any */
'use client';

import React, { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import { api } from '@/lib/api';
import { 
  Play, 
  Trash2, 
  AlertTriangle, 
  Compass,
  Crosshair,
  Route
} from 'lucide-react';

export default function AttackGraphView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<any>(null);
  const [loading, setLoading] = useState(true);
  
  // Interactive UI State
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [attackType, setAttackType] = useState<string>('RANSOMWARE');
  const [riskFactor, setRiskFactor] = useState<number>(0.5);
  const [simResults, setSimResults] = useState<any>(null);
  const [runningSim, setRunningSim] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  // Blast radius state
  const [blastNodeId, setBlastNodeId] = useState<string>('');
  const [maxHops, setMaxHops] = useState<number>(3);
  const [blastResult, setBlastResult] = useState<any>(null);
  const [runningBlast, setRunningBlast] = useState(false);

  // Attack paths state
  const [pathFrom, setPathFrom] = useState<string>('');
  const [pathTo, setPathTo] = useState<string>('');
  const [pathResult, setPathResult] = useState<any>(null);
  const [runningPaths, setRunningPaths] = useState(false);

  // Prefill analysis inputs when a node is clicked on the graph
  useEffect(() => {
    if (selectedNode?.id) {
      setBlastNodeId((prev) => prev || selectedNode.id);
      setPathFrom((prev) => prev || selectedNode.id);
    }
  }, [selectedNode]);

  // Dynamically import Cytoscape on the client side
  useEffect(() => {
    let active = true;
    let timer: any;
    
    const initGraph = async () => {
      try {
        setLoading(true);
        
        // Fetch current topology
        const topRes = await api.getTopology();
        if (!active) return;
        
        // Delay graph creation slightly to ensure container is fully bound and visible in the DOM
        timer = setTimeout(() => {
          if (!containerRef.current || !active) {
            console.warn("Container ref is not ready or inactive");
            return;
          }
          
          // Convert to cytoscape element format
          const cyElements = [
            ...(topRes.nodes || []).map((n: any) => ({
              data: { 
                id: n.id, 
                label: `${n.label}\n${n.id.substring(0, 8)}`, 
                type: n.label,
                ...n.properties 
              }
            })),
            ...(topRes.edges || []).map((e: any) => ({
              data: { 
                id: e.id, 
                source: e.source, 
                target: e.target, 
                label: e.type,
                type: e.type,
                ...e.properties 
              }
            }))
          ];

          console.log("[AttackGraph] Initializing Cytoscape with elements:", cyElements);

          // Initialize cytoscape instance
          const cy = cytoscape({
            container: containerRef.current,
            elements: cyElements,
            style: [
              {
                selector: 'node',
                style: {
                  'label': 'data(label)',
                  'color': '#cbd5e1',
                  'font-size': '8px',
                  'text-valign': 'bottom',
                  'text-margin-y': 4,
                  'background-color': '#1e293b',
                  'border-width': 1.5,
                  'border-color': '#475569',
                  'width': 30,
                  'height': 30,
                  'transition-property': 'background-color, border-color, border-width',
                  'transition-duration': 0.3
                }
              },
              {
                selector: 'node[type = "Host"]',
                style: {
                  'background-color': '#1d4ed8',
                  'border-color': '#3b82f6',
                  'shape': 'ellipse'
                }
              },
              {
                selector: 'node[type = "User"]',
                style: {
                  'background-color': '#6d28d9',
                  'border-color': '#8b5cf6',
                  'shape': 'round-rectangle'
                }
              },
              {
                selector: 'node[type = "Asset"]',
                style: {
                  'background-color': '#be185d',
                  'border-color': '#ec4899',
                  'shape': 'diamond',
                  'width': 34,
                  'height': 34
                }
              },
              {
                selector: 'node[type = "IP"]',
                style: {
                  'background-color': '#0f766e',
                  'border-color': '#14b8a6',
                  'shape': 'hexagon'
                }
              },
              {
                selector: 'edge',
                style: {
                  'line-color': '#334155',
                  'target-arrow-color': '#334155',
                  'target-arrow-shape': 'triangle',
                  'width': 1,
                  'curve-style': 'bezier',
                  'font-size': '6px',
                  'color': '#64748b',
                  'label': 'data(label)',
                  'text-background-opacity': 0.7,
                  'text-background-color': '#0f172a',
                  'text-background-padding': '2px',
                  'transition-property': 'line-color, width',
                  'transition-duration': 0.3
                }
              },
              {
                selector: 'edge[type = "SIMULATED_ATTACK"]',
                style: {
                  'line-color': '#ef4444',
                  'target-arrow-color': '#ef4444',
                  'width': 2.5,
                  'line-style': 'dashed'
                }
              },
              {
                selector: ':selected',
                style: {
                  'border-color': '#fbbf24',
                  'border-width': 3,
                  'line-color': '#fbbf24',
                  'target-arrow-color': '#fbbf24'
                }
              }
            ],
            layout: {
              name: 'cose',
              idealEdgeLength: 100,
              nodeOverlap: 20,
              refresh: 20,
              fit: true,
              padding: 30,
              randomize: false,
              componentSpacing: 100,
              nodeRepulsion: 400000,
              edgeElasticity: 100,
              nestingFactor: 5,
              gravity: 80,
              numIter: 1000,
              initialTemp: 200,
              coolingFactor: 0.95,
              minTemp: 1.0
            }
          });

          cy.on('tap', 'node', (evt: any) => {
            const node = evt.target;
            setSelectedNode({
              id: node.id(),
              label: node.data('type'),
              properties: node.data()
            });
          });

          cyRef.current = cy;
          
          // Force proper dimensions and sizing
          cy.resize();
          cy.fit();
          
          setLogs(prev => ['Graph: Digital Twin topology loaded from Neo4j.', ...prev]);
        }, 300);
        
      } catch (err) {
        console.error('Failed to init cytoscape:', err);
        setLogs(prev => ['Graph Error: Neo4j engine offline. Operating in mocked client view.', ...prev]);
      } finally {
        setLoading(false);
      }
    };

    initGraph();

    return () => {
      active = false;
      if (timer) clearTimeout(timer);
      if (cyRef.current) cyRef.current.destroy();
    };
  }, []);

  const handleSimulate = async () => {
    if (!selectedNode) return;
    setRunningSim(true);
    setSimResults(null);
    setLogs(prev => [`Sim: Starting ${attackType} simulation from ${selectedNode.id}...`, ...prev]);
    
    try {
      const res = await api.simulateAttack(selectedNode.id, attackType, riskFactor);
      setSimResults(res);
      setLogs(prev => [
        `Sim: Successfully simulated. Blast Radius Score: ${res.blast_radius_score * 100}%. ${res.critical_assets_at_risk} critical assets exposed.`,
        ...prev
      ]);
      
      // Update Cytoscape elements dynamically to add the simulated edges
      if (cyRef.current && res.affected_edges) {
        // Highlight compromised paths in Red
        res.affected_nodes.forEach((n: any) => {
          cyRef.current.$(`#${n.id}`).style({
            'background-color': '#ef4444',
            'border-color': '#f87171',
            'border-width': 2.5
          });
        });
        
        res.affected_edges.forEach((e: any, idx: number) => {
          const edgeId = `sim-edge-${idx}`;
          cyRef.current.add({
            data: {
              id: edgeId,
              source: e.source,
              target: e.target,
              label: `SIMULATED (${Math.round(e.probability*100)}%)`,
              type: 'SIMULATED_ATTACK'
            }
          });
        });
      }
    } catch (e: any) {
      // Mock fallback if Neo4j is offline
      setLogs(prev => [
        `Sim Error: ${e.message}`,
        `Sim (Mock): Compromised 2 downstream nodes. Highlighted predicted lateral paths.`,
        ...prev
      ]);
      
      if (cyRef.current) {
        const connectedEdges = cyRef.current.$(`#${selectedNode.id}`).connectedEdges();
        connectedEdges.forEach((edge: any) => {
          edge.style({
            'line-color': '#ef4444',
            'width': 2.5,
            'line-style': 'dashed'
          });
          edge.target().style({
            'background-color': '#ef4444',
            'border-color': '#f87171'
          });
        });
      }
    } finally {
      setRunningSim(false);
    }
  };

  const handleCleanup = async () => {
    setLogs(prev => ['Graph: Clearing simulated paths...', ...prev]);
    try {
      await api.cleanupSimulations();
      setSimResults(null);
      setLogs(prev => ['Graph: Simulated paths removed from Neo4j.', ...prev]);
      
      // Reload topology to reset styling
      if (cyRef.current) {
        const topRes = await api.getTopology();
        cyRef.current.elements().remove();
        
        const cyElements = [
          ...(topRes.nodes || []).map((n: any) => ({
            data: { id: n.id, label: `${n.label}\n${n.id.substring(0, 8)}`, type: n.label, ...n.properties }
          })),
          ...(topRes.edges || []).map((e: any) => ({
            data: { id: e.id, source: e.source, target: e.target, label: e.type, type: e.type, ...e.properties }
          }))
        ];
        cyRef.current.add(cyElements);
        cyRef.current.layout({ name: 'cose' }).run();
      }
    } catch (e: any) {
      console.error(e);
      // Reset styles locally anyway
      if (cyRef.current) {
        cyRef.current.elements().removeStyle();
        setLogs(prev => ['Graph (Mock): Local visual paths cleared.', ...prev]);
      }
    }
  };


  const handleBlastRadius = async () => {
    if (!blastNodeId.trim()) return;
    setRunningBlast(true);
    setBlastResult(null);
    setLogs(prev => [`Blast: Computing BFS blast radius from ${blastNodeId.trim()} (max ${maxHops} hops)...`, ...prev]);
    try {
      const res = await api.getBlastRadius(blastNodeId.trim(), 'Host', maxHops);
      setBlastResult(res);
      // Highlight reached nodes on the graph
      if (cyRef.current && res.nodes) {
        cyRef.current.elements().removeStyle();
        res.nodes.forEach((n: any) => {
          cyRef.current.$(`#${n.id}`).style({
            'background-color': '#f97316',
            'border-color': '#fdba74',
            'border-width': 2.5
          });
        });
        cyRef.current.$(`#${res.node_id}`).style({
          'background-color': '#ef4444',
          'border-color': '#fca5a5',
          'border-width': 3.5
        });
      }
      setLogs(prev => [
        `Blast: ${res.nodes_affected} node(s) reachable, score ${Math.round((res.blast_radius_score || 0) * 100)}%. Critical reached: ${(res.critical_assets_reached || []).length}.`,
        ...prev
      ]);
    } catch (e: any) {
      setLogs(prev => [`Blast Error: ${e.message}`, ...prev]);
    } finally {
      setRunningBlast(false);
    }
  };

  const handleAttackPaths = async () => {
    if (!pathFrom.trim() || !pathTo.trim()) return;
    setRunningPaths(true);
    setPathResult(null);
    setLogs(prev => [`Paths: Finding attack paths ${pathFrom.trim()} → ${pathTo.trim()}...`, ...prev]);
    try {
      const res = await api.getAttackPaths(pathFrom.trim(), pathTo.trim());
      setPathResult(res);
      // Highlight the first (shortest) path on the graph
      if (cyRef.current && res.paths && res.paths.length > 0) {
        cyRef.current.elements().removeStyle();
        res.paths[0].forEach((id: string) => {
          cyRef.current.$(`#${id}`).style({
            'background-color': '#8b5cf6',
            'border-color': '#c4b5fd',
            'border-width': 2.5
          });
        });
      }
      setLogs(prev => [
        res.path_count > 0
          ? `Paths: ${res.path_count} shortest path(s), ${res.shortest_hops} hop(s).`
          : `Paths: no path exists between the nodes.`,
        ...prev
      ]);
    } catch (e: any) {
      setLogs(prev => [`Paths Error: ${e.message}`, ...prev]);
    } finally {
      setRunningPaths(false);
    }
  };
  return (
    <div className="h-[calc(100vh-4rem)] flex overflow-hidden">
      
      {/* Topology Canvas */}
      <div className="flex-1 h-full bg-slate-950 relative border-r border-slate-800">
        {loading && (
          <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm z-20 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"></div>
          </div>
        )}
        <div ref={containerRef} style={{ width: '100%', height: '100%', minHeight: '500px', display: 'block' }} />
      </div>

      {/* Control Panel Sidebar */}
      <aside className="w-80 bg-slate-900 flex-shrink-0 flex flex-col h-full overflow-y-auto border-slate-800">
        
        {/* Selected Entity Card */}
        <div className="p-5 border-b border-slate-800">
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider mb-3 flex items-center gap-1.5">
            <Compass className="w-4 h-4 text-blue-500" /> Selected Node Context
          </h3>
          
          {selectedNode ? (
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-2 text-xs">
              <div>
                <span className="text-slate-500">Node Identifier:</span>
                <p className="font-mono font-bold text-slate-200 truncate mt-0.5">{selectedNode.id}</p>
              </div>
              <div className="flex justify-between">
                <div>
                  <span className="text-slate-500">Type:</span>
                  <p className="font-bold text-slate-300">{selectedNode.label}</p>
                </div>
                {selectedNode.properties.criticality && (
                  <div>
                    <span className="text-slate-500">Criticality:</span>
                    <p className={`font-bold uppercase ${
                      selectedNode.properties.criticality === 'Critical' ? 'text-red-400' : 'text-slate-400'
                    }`}>{selectedNode.properties.criticality}</p>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="text-xs text-slate-500 bg-slate-950/40 border border-dashed border-slate-850 p-4 rounded-xl text-center">
              Click any node in the Attack Graph to perform simulations.
            </div>
          )}
        </div>

        {/* What-If Attack Simulator */}
        <div className="p-5 border-b border-slate-800 space-y-4">
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
            <Play className="w-4 h-4 text-emerald-500" /> What-If Attack Simulator
          </h3>

          <div className="space-y-3">
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Scenario Type</label>
              <select
                value={attackType}
                onChange={e => setAttackType(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-blue-500 transition-all text-slate-200"
              >
                <option value="RANSOMWARE">Ransomware Spread</option>
                <option value="CREDENTIAL_THEFT">Credential Theft</option>
                <option value="PRIVILEGE_ESCALATION">Privilege Escalation</option>
                <option value="LATERAL_MOVEMENT">Lateral Movement</option>
              </select>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Risk Factor ({riskFactor})</label>
              <input
                type="range"
                min="0.1"
                max="1.0"
                step="0.1"
                value={riskFactor}
                onChange={e => setRiskFactor(parseFloat(e.target.value))}
                className="w-full h-1 bg-slate-950 rounded-lg appearance-none cursor-pointer accent-blue-500"
              />
            </div>

            <div className="flex gap-2 pt-2">
              <button
                onClick={handleSimulate}
                disabled={!selectedNode || runningSim}
                className="flex-1 bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 disabled:opacity-50 text-white font-semibold py-2 rounded-lg text-xs transition-all flex items-center justify-center gap-1.5 shadow-lg shadow-red-900/10 active:scale-[0.98]"
              >
                <Play className="w-3.5 h-3.5" /> {runningSim ? 'Simulating...' : 'Run Simulation'}
              </button>
              <button
                onClick={handleCleanup}
                className="bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-white p-2 rounded-lg transition-all"
                title="Clear Simulation"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Blast Radius Analysis */}
        <div className="p-5 border-b border-slate-800 space-y-4">
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
            <Crosshair className="w-4 h-4 text-orange-500" /> Blast Radius Analysis
          </h3>

          <div className="space-y-3">
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Compromised Node ID</label>
              <input
                type="text"
                value={blastNodeId}
                onChange={e => setBlastNodeId(e.target.value)}
                placeholder="e.g. ws-001 (click a node to prefill)"
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-orange-500 transition-all text-slate-200 placeholder:text-slate-600"
              />
            </div>

            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Max Hops ({maxHops})</label>
              <input
                type="range"
                min="1"
                max="10"
                step="1"
                value={maxHops}
                onChange={e => setMaxHops(parseInt(e.target.value, 10))}
                className="w-full h-1 bg-slate-950 rounded-lg appearance-none cursor-pointer accent-orange-500"
              />
            </div>

            <button
              onClick={handleBlastRadius}
              disabled={!blastNodeId.trim() || runningBlast}
              className="w-full bg-gradient-to-r from-orange-600 to-amber-600 hover:from-orange-500 hover:to-amber-500 disabled:opacity-50 text-white font-semibold py-2 rounded-lg text-xs transition-all flex items-center justify-center gap-1.5 shadow-lg shadow-orange-900/10 active:scale-[0.98]"
            >
              <Crosshair className="w-3.5 h-3.5" /> {runningBlast ? 'Computing...' : 'Compute Blast Radius'}
            </button>
          </div>

          {blastResult && (
            <div className="space-y-2 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-slate-950 border border-slate-850 p-2.5 rounded-lg">
                  <span className="text-[10px] text-slate-500 uppercase font-bold">Blast Score</span>
                  <p className="text-lg font-bold text-orange-400 mt-1">{Math.round((blastResult.blast_radius_score || 0) * 100)}%</p>
                </div>
                <div className="bg-slate-950 border border-slate-850 p-2.5 rounded-lg">
                  <span className="text-[10px] text-slate-500 uppercase font-bold">Nodes Reached</span>
                  <p className="text-lg font-bold text-orange-400 mt-1">{blastResult.nodes_affected}</p>
                </div>
              </div>
              {blastResult.critical_assets_reached?.length > 0 && (
                <div className="bg-red-950/30 border border-red-800/40 rounded-lg p-2.5">
                  <span className="text-[10px] text-red-400 uppercase font-bold">Critical assets in blast radius</span>
                  <div className="mt-1 space-y-0.5">
                    {blastResult.critical_assets_reached.map((h: string) => (
                      <p key={h} className="font-mono text-[10px] text-red-300 truncate">{h}</p>
                    ))}
                  </div>
                </div>
              )}
              <p className="text-[10px] text-slate-600">Model: {blastResult.model || 'heuristic-bfs-v1'} · BFS over asset topology</p>
            </div>
          )}
        </div>

        {/* Attack Path Finder */}
        <div className="p-5 border-b border-slate-800 space-y-4">
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
            <Route className="w-4 h-4 text-violet-500" /> Attack Path Finder
          </h3>

          <div className="space-y-3">
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">From Node</label>
              <input
                type="text"
                value={pathFrom}
                onChange={e => setPathFrom(e.target.value)}
                placeholder="source node id"
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-violet-500 transition-all text-slate-200 placeholder:text-slate-600"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">To Node</label>
              <input
                type="text"
                value={pathTo}
                onChange={e => setPathTo(e.target.value)}
                placeholder="target node id"
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-violet-500 transition-all text-slate-200 placeholder:text-slate-600"
              />
            </div>

            <button
              onClick={handleAttackPaths}
              disabled={!pathFrom.trim() || !pathTo.trim() || runningPaths}
              className="w-full bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 disabled:opacity-50 text-white font-semibold py-2 rounded-lg text-xs transition-all flex items-center justify-center gap-1.5 shadow-lg shadow-violet-900/10 active:scale-[0.98]"
            >
              <Route className="w-3.5 h-3.5" /> {runningPaths ? 'Searching...' : 'Find Attack Paths'}
            </button>
          </div>

          {pathResult && (
            <div className="space-y-2 text-xs">
              {pathResult.path_count > 0 ? (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-slate-950 border border-slate-850 p-2.5 rounded-lg">
                      <span className="text-[10px] text-slate-500 uppercase font-bold">Paths Found</span>
                      <p className="text-lg font-bold text-violet-400 mt-1">{pathResult.path_count}</p>
                    </div>
                    <div className="bg-slate-950 border border-slate-850 p-2.5 rounded-lg">
                      <span className="text-[10px] text-slate-500 uppercase font-bold">Shortest</span>
                      <p className="text-lg font-bold text-violet-400 mt-1">{pathResult.shortest_hops} hops</p>
                    </div>
                  </div>
                  <div className="bg-slate-950 border border-slate-850 rounded-lg p-2.5 space-y-1.5 max-h-40 overflow-y-auto">
                    {pathResult.paths.map((p: string[], i: number) => (
                      <p key={i} className="font-mono text-[10px] text-slate-400 leading-relaxed break-all">
                        <span className="text-violet-500 font-bold">{i + 1}.</span> {p.join(' → ')}
                      </p>
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-[11px] text-slate-500 bg-slate-950/60 border border-dashed border-slate-800 rounded-lg p-3 text-center">
                  {pathResult.message || 'No path exists between the nodes.'}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Simulation Output Stats */}
        {simResults && (
          <div className="p-5 border-b border-slate-800 space-y-3 bg-red-950/5 border-l-2 border-l-red-500">
            <h4 className="text-xs font-bold text-red-400 uppercase tracking-wider flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5" /> Threat Analysis Results
            </h4>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-slate-950 border border-slate-850 p-2.5 rounded-lg">
                <span className="text-[10px] text-slate-500 uppercase font-bold">Blast Radius</span>
                <p className="text-lg font-bold text-red-400 mt-1">{Math.round(simResults.blast_radius_score * 100)}%</p>
              </div>
              <div className="bg-slate-950 border border-slate-850 p-2.5 rounded-lg">
                <span className="text-[10px] text-slate-500 uppercase font-bold">Exposed Assets</span>
                <p className="text-lg font-bold text-red-400 mt-1">{simResults.critical_assets_at_risk}</p>
              </div>
            </div>
          </div>
        )}

        {/* Logs Console */}
        <div className="p-5 flex-1 flex flex-col min-h-[160px]">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Graph Engine Console</h3>
          <div className="flex-1 bg-slate-950 border border-slate-850 rounded-xl p-3 font-mono text-[9px] text-slate-400 space-y-1.5 overflow-y-auto h-32">
            {logs.map((log, idx) => (
              <div key={idx} className="leading-normal">
                <span className="text-slate-600">&gt;</span> {log}
              </div>
            ))}
          </div>
        </div>

      </aside>
    </div>
  );
}
