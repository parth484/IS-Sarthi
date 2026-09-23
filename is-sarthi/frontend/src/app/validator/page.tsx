'use client';

import React, { useState } from 'react';
import { ShieldAlert, AlertTriangle, ShieldCheck, CheckCircle2, Lightbulb, Loader2 } from 'lucide-react';
import { validateSpecification } from '@/lib/api';
import { ValidateResponse } from '@/lib/types';

const SAMPLE_1 = `Notice Inviting Tender (NIT) for Substation Foundation Works:
1. All cement used in RCC structural works shall strictly conform to IS 8112:1989 for 43 grade ordinary portland cement.
2. The reinforcement steel shall conform to IS 1786.
3. Aggregate testing shall comply with IS 383.`;

const SAMPLE_2 = `Procurement Specification for LV Power Supply:
1. Power cables shall be 1100V grade 3-core copper conductor conforming to IS 1554 (Part 1).
2. Installation shall be underground in trenches as per standard CPWD guidelines.`;

export default function ValidatorPage() {
  const [specText, setSpecText] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ValidateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAudit = async () => {
    if (!specText.trim()) return;
    setLoading(true);
    setError(null);

    try {
      const res = await validateSpecification(specText);
      setResult(res);
    } catch (err: any) {
      setError(err.message || 'Validation failed');
    } finally {
      setLoading(false);
    }
  };

  const highIssues = result?.issues.filter((i) => i.severity === 'high') ?? [];
  const medIssues = result?.issues.filter((i) => i.severity === 'medium') ?? [];

  return (
    <div className="space-y-6">
      {/* Title */}
      <div>
        <h2 className="text-xl sm:text-2xl font-bold text-govNavy-900 tracking-tight flex items-center gap-2">
          <ShieldAlert className="w-6 h-6 text-govSaffron-500" />
          <span>Tender Specification Audit & Validator</span>
        </h2>
        <p className="text-xs sm:text-sm text-slate-500 mt-1">
          Paste an existing procurement document or draft tender. The validator automatically extracts all Indian
          Standard citations, audits their currency, flags superseded/withdrawn standards, checks mandatory certification
          clauses, and suggests missing test methods.
        </p>
      </div>

      {/* Sample Buttons */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => setSpecText(SAMPLE_1)}
          className="text-left bg-white border border-slate-200 hover:border-blue-400 p-3 rounded-lg text-xs shadow-sm transition-all"
        >
          <span className="font-semibold text-slate-800 block">
            📄 Load Sample Spec with Superseded Cement Citation (IS 8112)
          </span>
          <span className="text-slate-500 text-[11px]">Cites IS 8112:1989, IS 1786, IS 383</span>
        </button>

        <button
          type="button"
          onClick={() => setSpecText(SAMPLE_2)}
          className="text-left bg-white border border-slate-200 hover:border-blue-400 p-3 rounded-lg text-xs shadow-sm transition-all"
        >
          <span className="font-semibold text-slate-800 block">
            📄 Load Sample Spec with Underground Cables (Missing Allied)
          </span>
          <span className="text-slate-500 text-[11px]">Cites IS 1554 (Part 1) missing test standards</span>
        </button>
      </div>

      {/* Input Text Area */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-5 shadow-sm space-y-4">
        <textarea
          value={specText}
          onChange={(e) => setSpecText(e.target.value)}
          rows={6}
          placeholder="Paste specification clauses containing IS 1554, IS 8112, IS 269, IS 1786, etc..."
          className="w-full border border-slate-300 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent text-slate-900 font-mono"
        />

        <div className="flex justify-end">
          <button
            type="button"
            onClick={handleAudit}
            disabled={loading || !specText.trim()}
            className="flex items-center gap-2 bg-govNavy-900 hover:bg-govNavy-800 text-white font-semibold px-6 py-2.5 rounded-lg text-sm shadow transition-colors disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldAlert className="w-4 h-4 text-govSaffron-500" />}
            <span>Run Full Compliance Audit</span>
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-300 text-red-900 p-4 rounded-xl text-sm">
          ⚠️ {error}
        </div>
      )}

      {/* Results Section */}
      {result && (
        <div className="space-y-5">
          {/* Summary Scorecards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-sm text-center">
              <span className="text-xs text-slate-500 font-medium">Cited Standards</span>
              <div className="text-2xl font-bold text-govNavy-900 mt-1">{result.cited.length}</div>
            </div>

            <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-sm text-center">
              <span className="text-xs text-slate-500 font-medium">Critical Superseded</span>
              <div
                className={`text-2xl font-bold mt-1 ${
                  highIssues.length > 0 ? 'text-red-600' : 'text-emerald-600'
                }`}
              >
                {highIssues.length}
              </div>
            </div>

            <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-sm text-center">
              <span className="text-xs text-slate-500 font-medium">Certification Warnings</span>
              <div className="text-2xl font-bold text-amber-600 mt-1">{medIssues.length}</div>
            </div>

            <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-sm text-center">
              <span className="text-xs text-slate-500 font-medium">Suggested Additions</span>
              <div className="text-2xl font-bold text-blue-600 mt-1">{result.suggested_additions.length}</div>
            </div>
          </div>

          {/* Critical Issues */}
          {highIssues.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 sm:p-5">
              <h4 className="text-base font-bold text-red-900 flex items-center gap-2 mb-3">
                <AlertTriangle className="w-5 h-5 text-red-600" />
                <span>Critical Defects: Superseded or Withdrawn Standards</span>
              </h4>
              <div className="space-y-3">
                {highIssues.map((iss, idx) => (
                  <div key={idx} className="bg-white border border-red-200 p-3 rounded-lg text-xs sm:text-sm">
                    <div className="font-bold text-red-800">{iss.is_number}: {iss.issue}</div>
                    <div className="text-slate-700 mt-1">
                      <strong>Recommended Action:</strong> {iss.action}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Compliance Warnings */}
          {medIssues.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 sm:p-5">
              <h4 className="text-base font-bold text-amber-900 flex items-center gap-2 mb-3">
                <ShieldCheck className="w-5 h-5 text-amber-600" />
                <span>Compliance Warnings: Mandatory Certification Clauses</span>
              </h4>
              <div className="space-y-3">
                {medIssues.map((iss, idx) => (
                  <div key={idx} className="bg-white border border-amber-200 p-3 rounded-lg text-xs sm:text-sm">
                    <div className="font-bold text-amber-800">{iss.is_number}: {iss.issue}</div>
                    <div className="text-slate-700 mt-1">
                      <strong>Recommended Action:</strong> {iss.action}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Validated Standards */}
          {result.cited.length > 0 && (
            <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-5">
              <h4 className="text-base font-bold text-slate-800 flex items-center gap-2 mb-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                <span>Validated Standards Mentioned</span>
              </h4>
              <div className="flex flex-wrap gap-2">
                {result.cited.map((c) => (
                  <span
                    key={c}
                    className="inline-flex items-center gap-1.5 bg-slate-100 border border-slate-200 px-3 py-1 rounded-md text-xs font-mono font-semibold text-slate-800"
                  >
                    <span>{c}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Suggested Additions */}
          {result.suggested_additions.length > 0 && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 sm:p-5">
              <h4 className="text-base font-bold text-blue-900 flex items-center gap-2 mb-2">
                <Lightbulb className="w-5 h-5 text-blue-600" />
                <span>Missing Allied Standards to Include in Acceptance Criteria</span>
              </h4>
              <p className="text-xs text-blue-800 mb-3">
                These standards are normative references of your cited items. Adding them defines acceptance testing and
                prevents legal disputes:
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                {result.suggested_additions.map((item) => (
                  <div key={item.is_number} className="bg-white border border-blue-100 p-2.5 rounded-md shadow-sm">
                    <div className="flex items-center justify-between font-mono font-bold text-govNavy-900">
                      <span>{item.is_number}</span>
                      <span className="text-[10px] bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded font-sans font-medium">
                        {item.role}
                      </span>
                    </div>
                    <div className="text-slate-600 text-[11px] mt-1 truncate" title={item.title}>
                      {item.title || 'Normative reference'}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5">
                      Referenced by {item.referenced_by}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
