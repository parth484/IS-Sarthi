'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Search, Sparkles, FileUp, Download, Loader2, RefreshCw, Building2, Globe } from 'lucide-react';
import { recommendStandards, extractDocumentText, fetchSampleTenders } from '@/lib/api';
import { Recommendation, ProcurementTender } from '@/lib/types';
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
  const [extractingDoc, setExtractingDoc] = useState(false);
  const [detectedLanguage, setDetectedLanguage] = useState<string | null>(null);
  const [normalizedQuery, setNormalizedQuery] = useState<string | null>(null);
  const [sampleTenders, setSampleTenders] = useState<ProcurementTender[]>([]);
  const [showTenders, setShowTenders] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchSampleTenders()
      .then(setSampleTenders)
      .catch(() => {});
  }, []);

  const handleSearch = async (overrideQuery?: string) => {
    const q = (overrideQuery ?? query).trim();
    if (!q) return;

    setLoading(true);
    setError(null);
    setResults(null);
    setDetectedLanguage(null);
    setNormalizedQuery(null);

    try {
      setStageMessage('Stage 1/3: Normalizing specification & computing dense/sparse embeddings...');
      await new Promise((r) => setTimeout(r, 120));

      setStageMessage('Stage 2/3: Traversing citation graph for normative closure & allied roles...');
      await new Promise((r) => setTimeout(r, 120));

      setStageMessage('Stage 3/3: Formulating tender compliance clauses & evaluating certification rules...');

      const res = await recommendStandards(q, topK, division);
      setDetectedLanguage(res.detected_language || null);
      setNormalizedQuery(res.normalized_query || null);

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

  const handleSelectTender = (tender: ProcurementTender) => {
    const spec = tender.raw_specification || tender.title;
    setQuery(spec);
    handleSearch(spec);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const lowerName = file.name.toLowerCase();
    const validExtensions = ['.pdf', '.docx', '.txt'];
    const isValid = validExtensions.some((ext) => lowerName.endsWith(ext));

    if (!isValid) {
      setError('Please upload a valid document (.pdf, .docx, or .txt).');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    if (file.size > 20 * 1024 * 1024) {
      setError('File size exceeds the 20 MB limit.');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    setExtractingDoc(true);
    setError(null);

    try {
      const data = await extractDocumentText(file);
      if (data.text) {
        setQuery(data.text);
      } else {
        setError('No readable text found in this document. The file may be empty or contain only images.');
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to extract text from document.');
    } finally {
      setExtractingDoc(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
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
      lines.push(`- Status: ${r.status.toUpperCase()}`);
      lines.push(`- Current Edition: ${r.latest_version}`);
      if (r.superseded_by) lines.push(`- Consolidated into: ${r.superseded_by}`);
      if (r.amendments?.length) {
        lines.push(`- Amendments: ${r.amendments.map((a) => `Amdt ${a.number} (${a.date || ''})`).join(', ')}`);
      }
      lines.push(`- Confidence: ${r.band} (${r.confidence.toFixed(3)})`);
      lines.push(`- Scope Justification: ${r.justification}`);
      if (r.certification) {
        lines.push(`- Mandatory Certification Scheme: ${r.certification.scheme_label || r.certification.scheme}`);
      }
      if (r.tender_clause) {
        lines.push(`\n### Tender Specification Clause:\n\`\`\`\n${r.tender_clause}\n\`\`\`\n`);
      }
      lines.push('\n---\n');
    });

    const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `is_sarthi_report_${Date.now()}.md`;
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
          Enter a procurement description, component specification, or upload tender drafting documents (.pdf, .docx, .txt). The engine identifies
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

      {/* Procurement Portal Integration (GeM Adapter Feed) */}
      {sampleTenders.length > 0 && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-govNavy-900 flex items-center gap-1.5">
              <Building2 className="w-4 h-4 text-govSaffron-500" />
              <span>Government e-Marketplace (GeM) Tender Connector:</span>
            </span>
            <button
              type="button"
              onClick={() => setShowTenders(!showTenders)}
              className="text-xs text-blue-700 hover:text-blue-800 font-semibold"
            >
              {showTenders ? 'Hide Sample GeM Bids' : `Explore ${sampleTenders.length} Verified Public GeM Bids`}
            </button>
          </div>
          {showTenders && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-1">
              {sampleTenders.map((t) => (
                <div
                  key={t.tender_id}
                  onClick={() => handleSelectTender(t)}
                  className="bg-white border border-slate-200 hover:border-govSaffron-500 p-2.5 rounded-lg cursor-pointer transition-all text-xs shadow-xs"
                >
                  <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
                    <span className="font-bold text-govNavy-900">{t.tender_id}</span>
                    <span>{t.portal || 'GeM'}</span>
                  </div>
                  <div className="font-semibold text-slate-800 mt-1 line-clamp-1">{t.title}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">{t.organization}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Voice Dictation (Sarvam AI STT) */}
      <VoiceRecorder onTranscribe={(text) => setQuery(text)} />

      {/* Specification Input Form */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-5 shadow-sm space-y-4">
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs sm:text-sm font-semibold text-slate-800">
              Product Description or Technical Specification
            </label>
            <label
              className={`flex items-center gap-1 text-xs font-medium transition-colors ${
                extractingDoc ? 'text-slate-400 cursor-not-allowed' : 'text-blue-700 hover:text-blue-800 cursor-pointer'
              }`}
            >
              {extractingDoc ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-600" />
              ) : (
                <FileUp className="w-3.5 h-3.5" />
              )}
              <span>{extractingDoc ? 'Extracting Document...' : 'Upload Document (PDF, DOCX, TXT)'}</span>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                onChange={handleFileUpload}
                disabled={extractingDoc}
                className="hidden"
              />
            </label>
          </div>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            rows={4}
            placeholder="e.g. 3 core armoured copper conductor XLPE insulated cable for working voltages up to 1100 V... Or type in Hindi/Marathi"
            className="w-full border border-slate-300 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent text-slate-900 placeholder:text-slate-400"
          />
        </div>

        {/* Multilingual Query Translation Notification Banner */}
        {detectedLanguage && detectedLanguage !== 'en-IN' && normalizedQuery && (
          <div className="bg-indigo-50 border border-indigo-200 text-indigo-950 rounded-lg p-2.5 text-xs flex items-center gap-2">
            <Globe className="w-4 h-4 text-indigo-600 shrink-0" />
            <span>
              Query translated from <strong>{detectedLanguage === 'hi-IN' ? 'Hindi (हिन्दी)' : detectedLanguage === 'mr-IN' ? 'Marathi (मराठी)' : detectedLanguage}</strong> to English technical representation for retrieval: <em>"{normalizedQuery}"</em>
            </span>
          </div>
        )}

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
