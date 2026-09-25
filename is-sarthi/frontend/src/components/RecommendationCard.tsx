'use client';

import React, { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  FileText,
  Copy,
  Check,
  ThumbsUp,
  ThumbsDown,
} from 'lucide-react';
import { Recommendation } from '@/lib/types';
import VoicePlayer from './VoicePlayer';
import { submitFeedback } from '@/lib/api';

interface RecommendationCardProps {
  rec: Recommendation;
  query: string;
}

export default function RecommendationCard({ rec, query }: RecommendationCardProps) {
  const [showClause, setShowClause] = useState(false);
  const [showAllied, setShowAllied] = useState(false);
  const [copied, setCopied] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState<'positive' | 'negative' | null>(null);

  const status = rec.status.toLowerCase();
  const isSuperseded = status === 'superseded' || status === 'withdrawn';

  const copyClause = () => {
    if (rec.tender_clause) {
      navigator.clipboard.writeText(rec.tender_clause);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleFeedback = (verdict: 'relevant' | 'irrelevant') => {
    submitFeedback(rec.is_number, verdict, query);
    setFeedbackSent(verdict === 'relevant' ? 'positive' : 'negative');
  };

  // Status Badge Metadata
  const getStatusBadge = () => {
    switch (status) {
      case 'current':
        return (
          <span className="inline-flex items-center gap-1 bg-emerald-50 text-emerald-700 border border-emerald-300 px-2.5 py-0.5 rounded text-xs font-semibold">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            Current Standard
          </span>
        );
      case 'superseded':
        return (
          <span className="inline-flex items-center gap-1 bg-red-50 text-red-700 border border-red-300 px-2.5 py-0.5 rounded text-xs font-semibold">
            <AlertTriangle className="w-3.5 h-3.5 text-red-600" />
            Superseded
          </span>
        );
      case 'withdrawn':
        return (
          <span className="inline-flex items-center gap-1 bg-rose-50 text-rose-700 border border-rose-300 px-2.5 py-0.5 rounded text-xs font-semibold">
            <XCircle className="w-3.5 h-3.5 text-rose-600" />
            Withdrawn
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 bg-amber-50 text-amber-700 border border-amber-300 px-2.5 py-0.5 rounded text-xs font-semibold">
            <HelpCircle className="w-3.5 h-3.5 text-amber-600" />
            {rec.status}
          </span>
        );
    }
  };

  const getRoleIcon = (r: string) => {
    switch (r.toLowerCase()) {
      case 'test method':
        return '🧪';
      case 'safety':
        return '🛡️';
      case 'installation':
        return '🔧';
      case 'terminology':
        return '📖';
      case 'sampling':
        return '📊';
      case 'dimensions':
        return '📏';
      default:
        return '📦';
    }
  };

  const alliedRoles = rec.allied ? Object.entries(rec.allied) : [];
  const totalAlliedCount = alliedRoles.reduce((acc, [_, items]) => acc + items.length, 0);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm hover:border-slate-300 transition-all">
      {/* Top Row: IS Number, Version & Confidence Badge */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 border-b border-slate-100 pb-3">
          <div>
          <div className="flex items-center gap-2.5 flex-wrap">
            <h3 className="text-xl font-bold text-govNavy-900 tracking-tight">{rec.is_number}</h3>
            <span className="text-xs bg-slate-100 text-slate-700 border border-slate-200 px-2 py-0.5 rounded font-mono font-medium">
              Edition: {rec.latest_version}
            </span>
            {getStatusBadge()}
            {rec.superseded_by && (
              <span className="inline-flex items-center gap-1 bg-red-100 text-red-800 border border-red-200 px-2 py-0.5 rounded text-xs font-bold">
                Replaced by {rec.superseded_by}
              </span>
            )}
          </div>
          <h4 className="text-base font-semibold text-blue-900 mt-1.5">{rec.title}</h4>

          {/* Amendments UI (surfaced only when verified amendments exist) */}
          {rec.amendments && rec.amendments.length > 0 && (
            <div className="mt-2 flex items-center gap-1.5 flex-wrap text-xs">
              <span className="text-slate-600 font-semibold flex items-center gap-1">
                <span>📜 Gazette Amendments ({rec.amendments.length}):</span>
              </span>
              {rec.amendments.map((amdt) => (
                <span
                  key={amdt.number}
                  className="inline-flex items-center bg-blue-50 text-blue-800 border border-blue-200 px-2 py-0.5 rounded text-[11px] font-mono font-medium"
                >
                  Amdt {amdt.number} {amdt.date ? `(${amdt.date})` : ''}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="text-left sm:text-right shrink-0">
          <div className="inline-flex items-center gap-1.5 font-bold text-sm">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                rec.band === 'High' ? 'bg-emerald-500' : rec.band === 'Medium' ? 'bg-amber-500' : 'bg-red-500'
              }`}
            />
            <span
              className={
                rec.band === 'High'
                  ? 'text-emerald-700'
                  : rec.band === 'Medium'
                  ? 'text-amber-700'
                  : 'text-red-700'
              }
            >
              {rec.band} Confidence
            </span>
          </div>
          <div className="text-xs text-slate-500 mt-0.5">Score: {rec.confidence.toFixed(3)}</div>
        </div>
      </div>

      {/* Superseded Critical Banner */}
      {rec.superseded_by && (
        <div className="mt-3 bg-red-50 border-l-4 border-red-600 p-3 rounded-r text-xs sm:text-sm text-red-900">
          <p className="font-bold flex items-center gap-1.5 text-red-800">
            <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
            CRITICAL CURRENCY WARNING: Outdated Citation
          </p>
          <p className="mt-1 text-slate-700 leading-relaxed">
            This standard is <strong>{rec.status.toUpperCase()}</strong> and was consolidated into{' '}
            <strong className="text-red-800 underline">{rec.superseded_by}</strong>. Citing this standard in active
            public procurement will cause legal disqualifications and bidder disputes.
          </p>
        </div>
      )}

      {/* Scope Justification Callout */}
      {rec.justification && (
        <div className="mt-3 bg-slate-50 border-l-4 border-blue-600 p-3 rounded-r text-xs sm:text-sm text-slate-800">
          <p className="font-semibold text-blue-900 flex items-center gap-1.5">
            <span>💡 Scope Justification:</span>
          </p>
          <p className="mt-0.5 text-slate-700 leading-relaxed">{rec.justification}</p>
        </div>
      )}

      {/* Granular Mandatory Certification Callout (ISI / CRS / Hallmarking) */}
      {rec.certification && (rec.certification.mandatory || rec.certification.scheme) && (() => {
        const scheme = (rec.certification.scheme || 'ISI').toUpperCase();
        const product = rec.certification.product || 'this item';
        if (scheme === 'CRS') {
          return (
            <div className="mt-3 bg-indigo-50 border border-indigo-200 p-3 rounded-lg text-xs sm:text-sm text-indigo-950 flex items-start gap-2.5">
              <ShieldCheck className="w-5 h-5 text-indigo-600 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold text-indigo-900 flex items-center gap-2">
                  <span>MANDATORY BIS REGISTRATION (CRS SCHEME-II)</span>
                  <span className="text-[10px] bg-indigo-100 text-indigo-800 px-1.5 py-0.5 rounded font-semibold uppercase">
                    Compulsory Registration
                  </span>
                </span>
                <p className="text-indigo-800 mt-0.5 text-xs leading-relaxed">
                  Bidders <strong>must hold a valid BIS Registration Number (R-number)</strong> for {product}.
                  Products must bear the standard BIS Self-Declaration mark in compliance with Scheme-II of BIS (Conformity Assessment) Regulations.
                </p>
              </div>
            </div>
          );
        } else if (scheme === 'HALLMARKING') {
          return (
            <div className="mt-3 bg-amber-50 border border-amber-300 p-3 rounded-lg text-xs sm:text-sm text-amber-950 flex items-start gap-2.5">
              <ShieldCheck className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold text-amber-900 flex items-center gap-2">
                  <span>MANDATORY BIS HALLMARKING & HUID</span>
                  <span className="text-[10px] bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded font-semibold uppercase">
                    Precious Articles
                  </span>
                </span>
                <p className="text-amber-800 mt-0.5 text-xs leading-relaxed">
                  Supplied articles ({product}) <strong>must bear mandatory BIS Hallmarking</strong> with a 6-digit alphanumeric
                  Hallmarking Unique Identification (HUID) and certified fineness grade under BIS (Hallmarking) Regulations.
                </p>
              </div>
            </div>
          );
        } else {
          return (
            <div className="mt-3 bg-amber-50 border border-amber-200 p-3 rounded-lg text-xs sm:text-sm text-amber-900 flex items-start gap-2.5">
              <ShieldCheck className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold text-amber-900 flex items-center gap-2">
                  <span>MANDATORY CERTIFICATION: {rec.certification.scheme_label || 'BIS Product Certification (ISI Mark)'}</span>
                  <span className="text-[10px] bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded font-semibold uppercase">
                    Gazette QCO
                  </span>
                </span>
                <p className="text-amber-800 mt-0.5 text-xs leading-relaxed">
                  Bidders <strong>must hold an active BIS CM/L license</strong> to affix the ISI mark for {product}.
                  Supplying uncertified goods is legally prohibited under the Gazette Quality Control Order (QCO).
                </p>
              </div>
            </div>
          );
        }
      })()}

      {/* Allied Standards & Normative References */}
      {totalAlliedCount > 0 && (
        <div className="mt-3 border border-slate-200 rounded-lg overflow-hidden">
          <button
            type="button"
            onClick={() => setShowAllied(!showAllied)}
            className="w-full flex items-center justify-between px-3.5 py-2.5 bg-slate-50 hover:bg-slate-100 text-xs font-semibold text-slate-700 transition-colors"
          >
            <span>📚 Allied Standards & Normative References ({totalAlliedCount} identified)</span>
            {showAllied ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>

          {showAllied && (
            <div className="p-3.5 bg-white border-t border-slate-200 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              {alliedRoles.map(([role, items]) => (
                <div key={role} className="border border-slate-100 rounded-md p-2.5 bg-slate-50/50">
                  <h5 className="font-bold text-slate-800 mb-1.5 flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <span>{getRoleIcon(role)}</span>
                      <span>{role}</span>
                    </span>
                    <span className="text-[10px] bg-slate-200 text-slate-700 px-1.5 py-0.2 rounded font-normal">
                      {items.length}
                    </span>
                  </h5>
                  <ul className="space-y-1.5">
                    {items.slice(0, 5).map((it) => (
                      <li key={it.is_number} className="text-slate-700 flex items-baseline gap-1.5">
                        <code className="bg-white border border-slate-200 px-1 py-0.5 rounded font-mono text-[11px] font-semibold text-govNavy-800">
                          {it.is_number}
                        </code>
                        <span className="truncate flex-1" title={it.title}>
                          {it.title}
                        </span>
                        {it.hop && (
                          <span className="text-[10px] text-slate-400 shrink-0">(hop {it.hop})</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tender Clause Generator & Actions */}
      <div className="mt-4 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowClause(!showClause)}
            className="flex items-center gap-1.5 bg-slate-100 hover:bg-slate-200 text-slate-800 font-semibold px-3 py-1.5 rounded text-xs border border-slate-300 transition-colors"
          >
            <FileText className="w-3.5 h-3.5 text-blue-700" />
            {showClause ? 'Hide Tender Clause' : '📝 View Formatted Tender Clause'}
          </button>
        </div>

        {/* Feedback Buttons */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => handleFeedback('relevant')}
            disabled={feedbackSent !== null}
            className={`flex items-center gap-1 px-2.5 py-1 rounded border text-xs font-medium transition-colors ${
              feedbackSent === 'positive'
                ? 'bg-emerald-50 text-emerald-700 border-emerald-300 font-semibold'
                : 'bg-white hover:bg-slate-50 text-slate-600 border-slate-200'
            }`}
          >
            <ThumbsUp className="w-3 h-3 text-emerald-600" />
            <span>{feedbackSent === 'positive' ? 'Feedback Saved' : 'Relevant'}</span>
          </button>

          <button
            type="button"
            onClick={() => handleFeedback('irrelevant')}
            disabled={feedbackSent !== null}
            className={`flex items-center gap-1 px-2.5 py-1 rounded border text-xs font-medium transition-colors ${
              feedbackSent === 'negative'
                ? 'bg-red-50 text-red-700 border-red-300 font-semibold'
                : 'bg-white hover:bg-slate-50 text-slate-600 border-slate-200'
            }`}
          >
            <ThumbsDown className="w-3 h-3 text-red-600" />
            <span>{feedbackSent === 'negative' ? 'Recorded' : 'Irrelevant'}</span>
          </button>
        </div>
      </div>

      {/* Formatted Tender Clause Box */}
      {showClause && rec.tender_clause && (
        <div className="mt-3 bg-emerald-50/70 border border-emerald-200 rounded-lg p-3 text-xs">
          <div className="flex items-center justify-between pb-2 border-b border-emerald-200/60 mb-2">
            <span className="font-bold text-emerald-900">NIT / RFP Enforceable Clause:</span>
            <button
              type="button"
              onClick={copyClause}
              className="flex items-center gap-1 bg-white hover:bg-emerald-100 border border-emerald-300 text-emerald-800 px-2 py-0.5 rounded font-semibold transition-colors"
            >
              {copied ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
              {copied ? 'Copied!' : 'Copy to Clipboard'}
            </button>
          </div>
          <pre className="whitespace-pre-wrap font-mono text-[11px] text-emerald-950 leading-relaxed bg-white/70 p-2.5 rounded border border-emerald-200/50">
            {rec.tender_clause}
          </pre>
        </div>
      )}

      {/* Multilingual Voice Explanation (Sarvam AI TTS) */}
      <VoicePlayer
        isNumber={rec.is_number}
        title={rec.title}
        status={rec.status}
        justification={rec.justification}
        supersededBy={rec.superseded_by}
      />
    </div>
  );
}
