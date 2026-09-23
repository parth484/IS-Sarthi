'use client';

import React, { useState, useEffect } from 'react';
import { Network, Loader2, Info } from 'lucide-react';
import { fetchStandards, fetchStandardGraph } from '@/lib/api';
import { GraphResponse } from '@/lib/types';

export default function GraphPage() {
  const [standards, setStandards] = useState<string[]>([]);
  const [selectedStandard, setSelectedStandard] = useState('IS 1554-1');
  const [depth, setDepth] = useState(1);
  const [graphData, setGraphData] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchStandards()
      .then((res) => {
        const numbers = res.standards.map((s) => s.is_number).sort();
        setStandards(numbers);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedStandard) return;
    setLoading(true);
    setError(null);
    fetchStandardGraph(selectedStandard, depth)
      .then((res) => setGraphData(res))
      .catch((err) => setError(err.message || 'Failed to load graph'))
      .finally(() => setLoading(false));
  }, [selectedStandard, depth]);

  const targetNode = graphData?.nodes.find((n) => n.is_target);
  const otherNodes = graphData?.nodes.filter((n) => !n.is_target) ?? [];

  return (
    <div className="space-y-6">
      {/* Title */}
      <div>
        <h2 className="text-xl sm:text-2xl font-bold text-govNavy-900 tracking-tight flex items-center gap-2">
          <Network className="w-6 h-6 text-govSaffron-500" />
          <span>Interactive Dependency Graph (Normative Closure)</span>
        </h2>
        <p className="text-xs sm:text-sm text-slate-500 mt-1">
          Standards do not exist in isolation. A product standard relies on test methods, materials, and safety codes.
          Explore the dependency tree for any Indian Standard.
        </p>
      </div>

      {/* Control Bar */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <span className="text-xs font-semibold text-slate-700 whitespace-nowrap">Select Standard:</span>
          <select
            value={selectedStandard}
            onChange={(e) => setSelectedStandard(e.target.value)}
            className="w-full sm:w-64 bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs font-bold text-govNavy-900 focus:outline-none focus:ring-2 focus:ring-blue-600"
          >
            {standards.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto">
          <span className="text-xs font-semibold text-slate-700">Graph Depth:</span>
          <select
            value={depth}
            onChange={(e) => setDepth(Number(e.target.value))}
            className="bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs font-bold text-govNavy-900 focus:outline-none focus:ring-2 focus:ring-blue-600"
          >
            <option value={1}>1 Hop (Direct References)</option>
            <option value={2}>2 Hops (Transitive Closure)</option>
          </select>
        </div>
      </div>

      {/* Target Node Overview */}
      {targetNode && (
        <div className="bg-blue-50/70 border border-blue-200 rounded-xl p-4 text-xs sm:text-sm flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <span className="text-xs uppercase tracking-wider text-blue-700 font-bold">Target Standard</span>
            <h3 className="text-base font-bold text-govNavy-900 mt-0.5">
              {targetNode.id}: {targetNode.title}
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <span className="bg-white border border-blue-200 text-blue-900 px-2.5 py-1 rounded text-xs font-semibold">
              Division: {targetNode.division}
            </span>
            <span
              className={`px-2.5 py-1 rounded text-xs font-semibold ${
                targetNode.status === 'current'
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-red-100 text-red-800'
              }`}
            >
              Status: {targetNode.status}
            </span>
          </div>
        </div>
      )}

      {/* Loading or Error */}
      {loading && (
        <div className="h-64 bg-white border border-slate-200 rounded-xl flex items-center justify-center text-slate-500 text-sm gap-2">
          <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
          <span>Traversing citation graph...</span>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-900 p-4 rounded-xl text-sm">
          ⚠️ {error}
        </div>
      )}

      {/* Graph Visualizer & References Table */}
      {!loading && graphData && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Visual SVG Network Diagram */}
          <div className="lg:col-span-2 bg-white border border-slate-200 rounded-xl p-4 shadow-sm min-h-[420px] flex flex-col justify-between">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-4 text-xs text-slate-500 font-medium">
              <span>🕸️ Network Diagram ({graphData.nodes.length} nodes, {graphData.edges.length} edges)</span>
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 bg-blue-700 rounded-full"></span> Target
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 bg-emerald-500 rounded-full"></span> Current
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 bg-red-500 rounded-full"></span> Outdated
                </span>
              </div>
            </div>

            {/* SVG Interactive Canvas */}
            <div className="flex-1 flex items-center justify-center overflow-auto p-4">
              <svg viewBox="0 0 600 360" className="w-full h-full max-h-[360px]">
                {/* Center / Target Node */}
                <g transform="translate(180, 180)">
                  <rect
                    x="-90"
                    y="-28"
                    width="180"
                    height="56"
                    rx="8"
                    className="fill-govNavy-900 stroke-blue-600 stroke-2"
                  />
                  <text
                    x="0"
                    y="-4"
                    textAnchor="middle"
                    className="fill-white font-bold text-xs"
                  >
                    {targetNode?.id}
                  </text>
                  <text
                    x="0"
                    y="14"
                    textAnchor="middle"
                    className="fill-blue-200 text-[9px]"
                  >
                    (Target Standard)
                  </text>
                </g>

                {/* Satellite Connected Reference Nodes */}
                {otherNodes.map((node, i) => {
                  const total = otherNodes.length;
                  const angle = (i / total) * Math.PI * 1.8 - Math.PI / 1.1;
                  const radius = 170;
                  const cx = 180 + radius * Math.cos(angle);
                  const cy = 180 + radius * Math.sin(angle);

                  const isDefective = node.status === 'superseded' || node.status === 'withdrawn';
                  const edgeRole = graphData.edges.find((e) => e.target === node.id)?.role || 'reference';

                  return (
                    <g key={node.id}>
                      {/* Edge Line */}
                      <line
                        x1="180"
                        y1="180"
                        x2={cx}
                        y2={cy}
                        stroke="#94a3b8"
                        strokeWidth="1.5"
                        strokeDasharray={isDefective ? '4,4' : 'none'}
                      />
                      {/* Edge Label */}
                      <text
                        x={(180 + cx) / 2}
                        y={(180 + cy) / 2 - 4}
                        textAnchor="middle"
                        className="fill-slate-400 text-[8px] font-sans"
                      >
                        {edgeRole}
                      </text>

                      {/* Node Box */}
                      <g
                        transform={`translate(${cx}, ${cy})`}
                        onClick={() => setSelectedStandard(node.id)}
                        className="cursor-pointer group"
                      >
                        <rect
                          x="-55"
                          y="-18"
                          width="110"
                          height="36"
                          rx="6"
                          className={
                            isDefective
                              ? 'fill-red-50 stroke-red-400 stroke-1 group-hover:stroke-red-600'
                              : 'fill-emerald-50 stroke-emerald-400 stroke-1 group-hover:stroke-emerald-600'
                          }
                        />
                        <text
                          x="0"
                          y="-2"
                          textAnchor="middle"
                          className={`font-mono font-bold text-[10px] ${
                            isDefective ? 'fill-red-800' : 'fill-emerald-900'
                          }`}
                        >
                          {node.id}
                        </text>
                        <text
                          x="0"
                          y="10"
                          textAnchor="middle"
                          className="fill-slate-500 text-[8px]"
                        >
                          [{node.status}]
                        </text>
                      </g>
                    </g>
                  );
                })}
              </svg>
            </div>

            <p className="text-[11px] text-slate-400 text-center mt-2">
              💡 Click any referenced node to center and expand its dependency tree.
            </p>
          </div>

          {/* Normative References List */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col">
            <h4 className="text-sm font-bold text-govNavy-900 mb-3 pb-2 border-b border-slate-100 flex items-center justify-between">
              <span>📋 Direct References</span>
              <span className="text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-normal">
                {otherNodes.length} items
              </span>
            </h4>

            {otherNodes.length === 0 ? (
              <div className="p-4 text-xs text-slate-500 text-center my-auto">
                No normative references recorded in the seed catalog for this standard.
              </div>
            ) : (
              <div className="space-y-2.5 overflow-y-auto max-h-[380px] pr-1 text-xs">
                {otherNodes.map((node) => {
                  const edge = graphData.edges.find((e) => e.target === node.id);
                  return (
                    <div
                      key={node.id}
                      onClick={() => setSelectedStandard(node.id)}
                      className="border border-slate-100 p-2.5 rounded-lg hover:bg-slate-50 cursor-pointer transition-colors"
                    >
                      <div className="flex items-center justify-between font-mono font-bold text-govNavy-800">
                        <span>{node.id}</span>
                        <span className="text-[10px] bg-blue-50 text-blue-800 px-1.5 py-0.5 rounded font-sans font-medium">
                          {edge?.role || 'Normative'}
                        </span>
                      </div>
                      <div className="text-slate-600 text-[11px] mt-1 leading-snug truncate" title={node.title}>
                        {node.title}
                      </div>
                      <div className="mt-1 flex items-center justify-between text-[10px] text-slate-400">
                        <span>Division: {node.division}</span>
                        <span className={node.status === 'current' ? 'text-emerald-700 font-semibold' : 'text-red-700 font-semibold'}>
                          {node.status}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
