'use client';

import React, { useState, useEffect, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Network, Loader2, Info, Building2, Sparkles, ExternalLink, ArrowLeft } from 'lucide-react';
import { fetchStandards, fetchStandardGraph, getStandardDetailUrl } from '@/lib/api';
import { GraphResponse } from '@/lib/types';

function GraphContent() {
  const searchParams = useSearchParams();
  const paramStandard = searchParams?.get('standard') || searchParams?.get('is_number');

  const [standards, setStandards] = useState<string[]>([]);
  const [selectedStandard, setSelectedStandard] = useState<string>(() => {
    if (paramStandard) {
      try {
        return decodeURIComponent(paramStandard).trim();
      } catch {
        return paramStandard.trim();
      }
    }
    return 'IS 1554-1';
  });
  const [depth, setDepth] = useState(1);
  const [graphData, setGraphData] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (paramStandard) {
      try {
        const decoded = decodeURIComponent(paramStandard).trim();
        if (decoded) setSelectedStandard(decoded);
      } catch {
        setSelectedStandard(paramStandard.trim());
      }
    }
  }, [paramStandard]);

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
          <span>Normative Citation Dependency Graph</span>
        </h2>
        <p className="text-xs sm:text-sm text-slate-500 mt-1">
          Standards do not exist in isolation. A product standard relies on test methods, materials, and safety codes.
          Explore the dependency tree for any Indian Standard.
        </p>
      </div>

      {/* Control Bar: Selector & Depth */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-1 max-w-md">
          <span className="text-xs font-semibold text-slate-700 whitespace-nowrap">Select Standard:</span>
          <select
            value={selectedStandard}
            onChange={(e) => setSelectedStandard(e.target.value)}
            className="flex-1 bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 text-xs text-slate-800 font-medium focus:ring-1 focus:ring-blue-600 focus:outline-none"
          >
            {standards.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
            {/* Include custom or selected standard if not in the default seed list */}
            {selectedStandard && !standards.includes(selectedStandard) && (
              <option value={selectedStandard}>
                {selectedStandard} (Selected)
              </option>
            )}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-700">Traversal Depth:</span>
          <select
            value={depth}
            onChange={(e) => setDepth(Number(e.target.value))}
            className="bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-800 font-medium focus:ring-1 focus:ring-blue-600 focus:outline-none"
          >
            <option value={1}>1 Hop (Direct Normative References)</option>
            <option value={2}>2 Hops (Transitive Closure)</option>
          </select>
        </div>
      </div>

      {/* Target Node Overview */}
      {targetNode && (
        <div className="bg-blue-50/70 border border-blue-200 rounded-xl p-4 text-xs sm:text-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wider text-blue-700 font-bold">Target Standard</span>
              <Link
                href={getStandardDetailUrl(targetNode.id)}
                className="text-xs text-blue-700 hover:text-blue-900 hover:underline font-semibold inline-flex items-center gap-1"
              >
                <span>View Dossier</span>
                <ExternalLink className="w-3 h-3" />
              </Link>
            </div>
            <h3 className="text-base font-bold text-govNavy-900 mt-0.5">
              {targetNode.id}: {targetNode.title}
            </h3>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {otherNodes.length > 0 ? (
              <span className="inline-flex items-center gap-1 bg-blue-50 text-blue-800 border border-blue-200 px-2.5 py-1 rounded text-xs font-semibold">
                <Sparkles className="w-3.5 h-3.5 text-blue-600" />
                <span>Seed Enriched Dossier</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 bg-slate-100 text-slate-800 border border-slate-300 px-2.5 py-1 rounded text-xs font-semibold">
                <Building2 className="w-3.5 h-3.5 text-slate-600" />
                <span>Official BIS Catalogue</span>
              </span>
            )}
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
                <g className="cursor-pointer" onClick={() => targetNode && setSelectedStandard(targetNode.id)}>
                  <circle cx="300" cy="180" r="32" className="fill-blue-700 stroke-blue-900 stroke-2" />
                  <text
                    x="300"
                    y="184"
                    textAnchor="middle"
                    className="fill-white font-mono font-bold text-[10px] pointer-events-none"
                  >
                    {targetNode ? targetNode.id.slice(0, 10) : 'Target'}
                  </text>
                  <text
                    x="300"
                    y="226"
                    textAnchor="middle"
                    className="fill-slate-700 font-sans font-bold text-[11px] pointer-events-none"
                  >
                    (Target Standard)
                  </text>
                </g>

                {/* Satellite Nodes in Circle */}
                {otherNodes.map((node, i) => {
                  const total = otherNodes.length;
                  const angle = (i * (2 * Math.PI)) / total;
                  const radius = 130;
                  const cx = 300 + radius * Math.cos(angle);
                  const cy = 180 + radius * Math.sin(angle);
                  const isCurrent = node.status === 'current';

                  return (
                    <g
                      key={node.id}
                      className="cursor-pointer group"
                      onClick={() => setSelectedStandard(node.id)}
                    >
                      <line
                        x1="300"
                        y1="180"
                        x2={cx}
                        y2={cy}
                        className="stroke-slate-300 stroke-1 stroke-dashed"
                      />
                      <circle
                        cx={cx}
                        cy={cy}
                        r="22"
                        className={`${
                          isCurrent ? 'fill-emerald-500 stroke-emerald-700' : 'fill-red-500 stroke-red-700'
                        } stroke-2 transition-transform duration-200 group-hover:scale-110`}
                      />
                      <text
                        x={cx}
                        y={cy + 3}
                        textAnchor="middle"
                        className="fill-white font-mono font-bold text-[9px] pointer-events-none"
                      >
                        {node.id.slice(0, 8)}
                      </text>
                      <text
                        x={cx}
                        y={cy + 32}
                        textAnchor="middle"
                        className="fill-slate-600 font-sans font-medium text-[9px] pointer-events-none"
                      >
                        {node.id}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>

            <p className="text-[11px] text-slate-400 text-center mt-2 border-t border-slate-100 pt-2">
              💡 Click on any satellite node to pivot the citation graph around that standard.
            </p>
          </div>

          {/* Connected Standards List */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col justify-between">
            <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3 pb-2 border-b border-slate-100">
              Connected Standards ({otherNodes.length})
            </h4>

            {otherNodes.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-400 text-xs py-8 text-center space-y-2">
                <Info className="w-8 h-8 text-slate-300" />
                <p className="font-semibold text-slate-700">Official BIS Catalogue Standard</p>
                <p className="text-[11px] text-slate-500 max-w-xs">
                  Normative citation networks are mapped for Tier 1 seed standards. Standard conformity specifications remain valid for this standard.
                </p>
                {targetNode && (
                  <Link
                    href={getStandardDetailUrl(targetNode.id)}
                    className="inline-flex items-center gap-1 text-xs text-blue-700 hover:underline font-semibold pt-1"
                  >
                    <span>View Catalogue Record →</span>
                  </Link>
                )}
              </div>
            ) : (
              <div className="space-y-2.5 overflow-y-auto max-h-[360px] pr-1">
                {otherNodes.map((node) => {
                  const edge = graphData.edges.find((e) => e.target === node.id);
                  return (
                    <div
                      key={node.id}
                      className="border border-slate-100 p-2.5 rounded-lg hover:bg-slate-50 transition-colors"
                    >
                      <div className="flex items-center justify-between font-mono font-bold text-govNavy-800">
                        <button
                          type="button"
                          onClick={() => setSelectedStandard(node.id)}
                          className="hover:text-blue-600 hover:underline text-left"
                        >
                          {node.id}
                        </button>
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] bg-blue-50 text-blue-800 px-1.5 py-0.5 rounded font-sans font-medium">
                            {edge?.role || 'Normative'}
                          </span>
                          <Link
                            href={getStandardDetailUrl(node.id)}
                            className="text-slate-400 hover:text-blue-600"
                            title="View dossier"
                          >
                            <ExternalLink className="w-3 h-3" />
                          </Link>
                        </div>
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

export default function GraphPage() {
  return (
    <Suspense
      fallback={
        <div className="h-64 bg-white border border-slate-200 rounded-xl flex items-center justify-center text-slate-500 text-sm gap-2">
          <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
          <span>Loading dependency graph explorer...</span>
        </div>
      }
    >
      <GraphContent />
    </Suspense>
  );
}
