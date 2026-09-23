'use client';

import React, { useState } from 'react';
import { Search, Sparkles, FileUp, Download, Loader2, RefreshCw } from 'lucide-react';
import { recommendStandards } from '@/lib/api';
import { Recommendation } from '@/lib/types';
import RecommendationCard from '@/components/RecommendationCard';
import VoiceRecorder from '@/components/VoiceRecorder';

const PRESET_QUERIES = [
  {
    icon: '⚡',
    label: '3-Core Armoured Cable',
    text: '3 core armoured copper cable for underground LV power distribution up to 1100V',
  },
  {
    icon: '🏗️',
    label: '43 Grade Cement (Superseded)',
    text: '43 grade ordinary portland cement for RCC foundation construction',
  },
  {
    icon: '🔩',
    label: 'TMT Fe 500 Steel Bars',
    text: 'High strength deformed steel bars Fe 500 grade for concrete reinforcement',
  },
  {
    icon: '🔌',
    label: 'Distribution Transformers',
    text: 'Outdoor type three phase oil immersed distribution transformers up to 2500 kVA',
  },
];

const DIVISIONS = ['All Divisions', 'ETD', 'CED', 'MTD'];

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(5);
  const [division, setDivision] = useState('All Divisions');
  const [loading, setLoading] = useState(false);
  const [stageMessage, setStageMessage] = useState('');
  const [results, setResults] = useState<Recommendation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (overrideQuery?: string) => {
    const q = (overrideQuery ?? query).trim();
    if (!q) return;

    setLoading(true);
    setError(null);
    setResults(null);

    try {
      setStageMessage('Stage 1/3: Computing dense & sparse hybrid embeddings...');
      await new Promise((r) => setTimeout(r, 120));

      setStageMessage('Stage 2/3: Traversing citation graph for normative closure & test methods...');
      await new Promise((r) => setTimeout(r, 120));

      setStageMessage('Stage 3/3: Evaluating Gazette QCO certification rules & formulating justifications...');

      const res = await recommendStandards(q, topK, division);
      if (res.state === 'low_confidence' || !res.recommendations?.length) {
        setError(res.message || 'No confident match found. Please include more specific technical attributes.');
        setResults([]);
      } else {
        setResults(res.recommendations);
      }
    } catch (err: any) {
      setError(err.message || 'Search failed. Please try again.');
    } finally {
      setLoading(false);
      setStageMessage('');
    }
  };

  const handlePreset = (presetText: string) => {
    setQuery(presetText);
    handleSearch(presetText);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      if (text) {
        setQuery(text.slice(0, 2000));
      }
    };
    reader.readAsText(file);
  };

  const downloadJson = () => {
    if (!results) return;
    const blob = new Blob([JSON.stringify({ query, recommendations: results }, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `is_sarthi_recommendation_${Date.now()}.json`;
    a.click();
  };

  const downloadMarkdown = () => {
    if (!results) return;
    const lines = [`# IS Sarthi Recommendation Report`, `Query: ${query}\n`];
    results.forEach((r) => {
      lines.push(`## ${r.is_number}: ${r.title}`);
      lines.push(`- Status: ${r.status} | Confidence: ${r.confidence}`);
      lines.push(`- Justification: ${r.justification}`);
      if (r.tender_clause) {
        lines.push(`- Tender Clause:\n\`\`\`\n${r.tender_clause}\n\`\`\`\n`);
      }
    });

    const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `is_sarthi_summary_${Date.now()}.md`;
    a.click();
  };

  return (
    <div className="space-y-6">
      {/* Top Banner Title */}
      <div>
        <h2 className="text-xl sm:text-2xl font-bold text-govNavy-900 tracking-tight flex items-center gap-2">
          <Search className="w-6 h-6 text-govSaffron-500" />
          <span>Recommend Applicable Standards for Procurement</span>
        </h2>
        <p className="text-xs sm:text-sm text-slate-500 mt-1">
          Enter a procurement description, component specification, or upload tender drafting text. The engine identifies
          primary standards, allied test methods, and mandatory certification rules.
        </p>
      </div>

      {/* Preset Chips */}
      <div>
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-govSaffron-500" />
          Quick Example Queries (Click to load):
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
          {PRESET_QUERIES.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => handlePreset(p.text)}
              className="text-left bg-white border border-slate-200 hover:border-blue-400 hover:bg-blue-50/50 p-2.5 rounded-lg shadow-sm transition-all text-xs group"
            >
              <span className="font-semibold text-slate-800 group-hover:text-blue-900 flex items-center gap-1.5">
                <span>{p.icon}</span>
                <span>{p.label}</span>
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Voice Dictation (Sarvam AI STT) */}
      <VoiceRecorder onTranscribe={(text) => setQuery(text)} />

      {/* Specification Input Form */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-5 shadow-sm space-y-4">
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs sm:text-sm font-semibold text-slate-800">
              Product Description or Technical Specification
            </label>
            <label className="flex items-center gap-1 text-xs text-blue-700 hover:text-blue-800 cursor-pointer font-medium">
              <FileUp className="w-3.5 h-3.5" />
              <span>Upload .txt File</span>
              <input type="file" accept=".txt" onChange={handleFileUpload} className="hidden" />
            </label>
          </div>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            rows={4}
            placeholder="e.g. 3 core armoured copper conductor XLPE insulated cable for working voltages up to 1100 V..."
            className="w-full border border-slate-300 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent text-slate-900 placeholder:text-slate-400"
          />
        </div>

        {/* Filter Row & Submit Button */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-600 font-medium">Max Results:</span>
              <select
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                className="bg-slate-50 border border-slate-300 rounded px-2.5 py-1.5 text-xs text-slate-800 font-medium"
              >
                <option value={3}>3 Standards</option>
                <option value={5}>5 Standards</option>
                <option value={8}>8 Standards</option>
                <option value={10}>10 Standards</option>
              </select>
            </div>

            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-600 font-medium">Division:</span>
              <select
                value={division}
                onChange={(e) => setDivision(e.target.value)}
                className="bg-slate-50 border border-slate-300 rounded px-2.5 py-1.5 text-xs text-slate-800 font-medium"
              >
                {DIVISIONS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <button
            type="button"
            onClick={() => handleSearch()}
            disabled={loading || !query.trim()}
            className="flex items-center justify-center gap-2 bg-govNavy-900 hover:bg-govNavy-800 text-white font-semibold px-6 py-2.5 rounded-lg text-sm shadow transition-colors disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4 text-govSaffron-500" />}
            <span>Find Standards & Allied Norms</span>
          </button>
        </div>

        {/* Staged Pipeline Progress */}
        {loading && stageMessage && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-xs text-blue-800 flex items-center gap-2 animate-pulse">
            <RefreshCw className="w-4 h-4 animate-spin text-blue-600" />
            <span>{stageMessage}</span>
          </div>
        )}
      </div>

      {/* Error / Warning Alert */}
      {error && (
        <div className="bg-amber-50 border border-amber-300 text-amber-900 p-4 rounded-xl text-sm">
          ⚠️ {error}
        </div>
      )}

      {/* Results Section */}
      {results && results.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold text-govNavy-900">
              🎯 Recommendations ({results.length} surfaced)
            </h3>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={downloadJson}
                className="flex items-center gap-1 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs px-2.5 py-1 rounded shadow-sm font-medium"
              >
                <Download className="w-3.5 h-3.5" />
                <span>JSON</span>
              </button>
              <button
                type="button"
                onClick={downloadMarkdown}
                className="flex items-center gap-1 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs px-2.5 py-1 rounded shadow-sm font-medium"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Markdown</span>
              </button>
            </div>
          </div>

          <div className="space-y-4">
            {results.map((rec) => (
              <RecommendationCard key={rec.is_number} rec={rec} query={query} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
