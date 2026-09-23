'use client';

import React, { useState, useEffect } from 'react';
import { BarChart3, Search, Layers, ShieldCheck, AlertTriangle, FileCheck } from 'lucide-react';
import { fetchStandards } from '@/lib/api';
import { StandardCatalogItem } from '@/lib/types';

export default function AnalyticsPage() {
  const [standards, setStandards] = useState<StandardCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchKw, setSearchKw] = useState('');
  const [divFilter, setDivFilter] = useState('All');

  useEffect(() => {
    fetchStandards()
      .then((res) => setStandards(res.standards))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const totalIndexed = standards.length;
  const mandatoryCount = standards.filter((s) => s.mandatory_qco).length;
  const supersededCount = standards.filter((s) => s.status === 'superseded' || s.status === 'withdrawn').length;

  const divisionCounts = standards.reduce((acc, s) => {
    acc[s.division] = (acc[s.division] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const divisionsList = Object.keys(divisionCounts).sort();

  const filtered = standards.filter((s) => {
    if (divFilter !== 'All' && s.division !== divFilter) return false;
    if (searchKw.trim()) {
      const kw = searchKw.toLowerCase();
      return (
        s.is_number.toLowerCase().includes(kw) ||
        s.title.toLowerCase().includes(kw) ||
        s.division.toLowerCase().includes(kw)
      );
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Title */}
      <div>
        <h2 className="text-xl sm:text-2xl font-bold text-govNavy-900 tracking-tight flex items-center gap-2">
          <BarChart3 className="w-6 h-6 text-govSaffron-500" />
          <span>Bureau of Indian Standards (BIS) Corpus Analytics</span>
        </h2>
        <p className="text-xs sm:text-sm text-slate-500 mt-1">
          Inspect catalog coverage, division distribution, and mandatory certification rules across the national standards
          corpus.
        </p>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-sm">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-xs font-medium">Indexed Standards</span>
            <FileCheck className="w-4 h-4 text-blue-600" />
          </div>
          <div className="text-2xl font-bold text-govNavy-900 mt-1">{totalIndexed}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">National standards seed</div>
        </div>

        <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-sm">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-xs font-medium">Active Divisions</span>
            <Layers className="w-4 h-4 text-indigo-600" />
          </div>
          <div className="text-2xl font-bold text-govNavy-900 mt-1">{divisionsList.length}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">ETD, CED, MTD</div>
        </div>

        <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-sm">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-xs font-medium">Mandatory ISI / QCO</span>
            <ShieldCheck className="w-4 h-4 text-amber-600" />
          </div>
          <div className="text-2xl font-bold text-amber-600 mt-1">{mandatoryCount}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Gazette enforceable</div>
        </div>

        <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-sm">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-xs font-medium">Superseded / Withdrawn</span>
            <AlertTriangle className="w-4 h-4 text-red-600" />
          </div>
          <div className="text-2xl font-bold text-red-600 mt-1">{supersededCount}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Outdated citations</div>
        </div>
      </div>

      {/* Main Grid: Division Distribution & Interactive Table */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Standards by Division */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <h3 className="text-sm font-bold text-govNavy-900 mb-4 pb-2 border-b border-slate-100 flex items-center justify-between">
            <span>Standards by Division</span>
            <span className="text-xs font-normal text-slate-500">{divisionsList.length} divisions</span>
          </h3>

          <div className="space-y-4 text-xs">
            {divisionsList.map((div) => {
              const count = divisionCounts[div];
              const pct = Math.round((count / (totalIndexed || 1)) * 100);
              return (
                <div key={div} className="space-y-1">
                  <div className="flex items-center justify-between font-semibold text-slate-700">
                    <span>{div} Division</span>
                    <span>
                      {count} ({pct}%)
                    </span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                    <div
                      className="bg-govNavy-800 h-2.5 rounded-full transition-all duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-6 pt-4 border-t border-slate-100 text-xs text-slate-500 space-y-1.5">
            <p>
              <strong>ETD</strong>: Electrotechnical Division
            </p>
            <p>
              <strong>CED</strong>: Civil Engineering Division
            </p>
            <p>
              <strong>MTD</strong>: Metallurgical Engineering Division
            </p>
          </div>
        </div>

        {/* Filterable Catalog Table */}
        <div className="lg:col-span-2 bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 pb-3 border-b border-slate-100">
            <h3 className="text-sm font-bold text-govNavy-900">
              Filterable Catalog ({filtered.length} standards)
            </h3>

            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search catalog..."
                  value={searchKw}
                  onChange={(e) => setSearchKw(e.target.value)}
                  className="bg-slate-50 border border-slate-300 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-600 w-44"
                />
              </div>

              <select
                value={divFilter}
                onChange={(e) => setDivFilter(e.target.value)}
                className="bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-800 font-medium"
              >
                <option value="All">All Divisions</option>
                {divisionsList.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Table */}
          <div className="flex-1 overflow-x-auto overflow-y-auto max-h-[460px] border border-slate-100 rounded-lg">
            <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
              <thead className="bg-slate-50 sticky top-0 font-semibold text-slate-700">
                <tr>
                  <th className="py-2.5 px-3">IS Number</th>
                  <th className="py-2.5 px-3">Title</th>
                  <th className="py-2.5 px-2">Div</th>
                  <th className="py-2.5 px-2">Status</th>
                  <th className="py-2.5 px-2">QCO</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
                {filtered.map((item) => (
                  <tr key={item.is_number} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-2 px-3 font-mono font-bold text-govNavy-900 whitespace-nowrap">
                      {item.is_number}
                    </td>
                    <td className="py-2 px-3 max-w-xs truncate" title={item.title}>
                      {item.title}
                    </td>
                    <td className="py-2 px-2 text-slate-500 font-medium whitespace-nowrap">{item.division}</td>
                    <td className="py-2 px-2 whitespace-nowrap">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold ${
                          item.status === 'current'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-red-50 text-red-700 border border-red-200'
                        }`}
                      >
                        {item.status}
                      </span>
                    </td>
                    <td className="py-2 px-2 whitespace-nowrap">
                      {item.mandatory_qco ? (
                        <span className="text-amber-700 font-semibold text-[11px]">Yes</span>
                      ) : (
                        <span className="text-slate-400 text-[11px]">No</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
