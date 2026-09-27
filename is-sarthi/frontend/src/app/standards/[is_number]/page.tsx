'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import {
  ArrowLeft,
  Building2,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  ShieldCheck,
  FileText,
  Copy,
  Check,
  Network,
  Info,
  Loader2,
  Calendar,
  Layers,
  BookOpen,
} from 'lucide-react';
import { fetchStandardDetail } from '@/lib/api';
import { StandardDetail } from '@/lib/types';

export default function StandardDetailPage() {
  const params = useParams();
  const rawIsNumber = params?.is_number as string;
  const isNumber = rawIsNumber ? decodeURIComponent(rawIsNumber) : '';

  const [standard, setStandard] = useState<StandardDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!isNumber) return;
    setLoading(true);
    setError(null);

    fetchStandardDetail(isNumber)
      .then((data) => setStandard(data))
      .catch((err) => setError(err.message || `Standard '${isNumber}' not found`))
      .finally(() => setLoading(false));
  }, [isNumber]);

  const copyClause = () => {
    if (standard?.tender_clause) {
      navigator.clipboard.writeText(standard.tender_clause);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const isEnriched = standard?.tier === 'enriched' || standard?.is_enriched === true;
  const status = (standard?.status || 'current').toLowerCase();

  const getStatusBadge = () => {
    switch (status) {
      case 'current':
        return (
          <span className="inline-flex items-center gap-1.5 bg-emerald-50 text-emerald-700 border border-emerald-300 px-3 py-1 rounded text-xs font-semibold">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            Current Standard
          </span>
        );
      case 'withdrawn':
        return (
          <span className="inline-flex items-center gap-1.5 bg-rose-50 text-rose-700 border border-rose-300 px-3 py-1 rounded text-xs font-semibold">
            <XCircle className="w-4 h-4 text-rose-600" />
            Withdrawn Standard
          </span>
        );
      case 'superseded':
        return (
          <span className="inline-flex items-center gap-1.5 bg-red-50 text-red-700 border border-red-300 px-3 py-1 rounded text-xs font-semibold">
            <AlertTriangle className="w-4 h-4 text-red-600" />
            Superseded Standard
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 bg-amber-50 text-amber-700 border border-amber-300 px-3 py-1 rounded text-xs font-semibold">
            <HelpCircle className="w-4 h-4 text-amber-600" />
            {standard?.status}
          </span>
        );
    }
  };

  const getTierBadge = () => {
    if (isEnriched) {
      return (
        <span
          title="Seed Enriched Dossier: includes technical scope, normative references, certification, amendments, and allied relationships"
          className="inline-flex items-center gap-1.5 bg-blue-50 text-blue-800 border border-blue-200 px-3 py-1 rounded text-xs font-semibold shadow-xs"
        >
          <Sparkles className="w-4 h-4 text-blue-600 shrink-0" />
          <span>Seed Enriched Dossier</span>
        </span>
      );
    }
    return (
      <span
        title="Official BIS Catalogue: national published standard with verified BIS catalogue metadata"
        className="inline-flex items-center gap-1.5 bg-slate-100 text-slate-800 border border-slate-300 px-3 py-1 rounded text-xs font-semibold shadow-xs"
      >
        <Building2 className="w-4 h-4 text-slate-600 shrink-0" />
        <span>Official BIS Catalogue</span>
      </span>
    );
  };

  if (loading) {
    return (
      <div className="min-h-[360px] bg-white border border-slate-200 rounded-xl p-8 flex flex-col items-center justify-center text-slate-500 gap-3">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
        <p className="text-sm font-medium">Resolving standard details across unified BIS corpus...</p>
      </div>
    );
  }

  if (error || !standard) {
    return (
      <div className="space-y-4">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-sm text-blue-700 hover:text-blue-900 font-semibold"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Recommendation Engine</span>
        </Link>
        <div className="bg-red-50 border border-red-200 text-red-900 p-6 rounded-xl">
          <h3 className="text-base font-bold flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-red-600" />
            <span>Standard Not Found</span>
          </h3>
          <p className="text-sm mt-1 text-slate-700">{error || `Could not find record for '${isNumber}'.`}</p>
        </div>
      </div>
    );
  }

  const alliedRoles = standard.allied_by_role ? Object.entries(standard.allied_by_role) : [];
  const totalAlliedCount = alliedRoles.reduce((acc, [_, items]) => acc + items.length, 0);

  return (
    <div className="space-y-6">
      {/* Top Breadcrumb Navigation */}
      <div>
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-xs sm:text-sm text-blue-700 hover:text-blue-900 font-semibold transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Recommendation Engine</span>
        </Link>
      </div>

      {/* Main Standard Header Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 border-b border-slate-100 pb-4">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h2 className="text-2xl sm:text-3xl font-bold text-govNavy-900 tracking-tight font-mono">
                {standard.is_number}
              </h2>
              {standard.year && (
                <span className="text-xs bg-slate-100 text-slate-700 border border-slate-200 px-2.5 py-1 rounded font-mono font-medium">
                  Year: {standard.year}
                </span>
              )}
              {getTierBadge()}
              {getStatusBadge()}
              {standard.superseded_by && (
                <span className="inline-flex items-center gap-1 bg-red-100 text-red-800 border border-red-200 px-2.5 py-1 rounded text-xs font-bold">
                  Replaced by {standard.superseded_by}
                </span>
              )}
            </div>

            <h3 className="text-lg sm:text-xl font-bold text-blue-950 mt-2 leading-snug">
              {standard.title}
            </h3>

            {standard.title_hindi && (
              <div className="text-sm text-slate-600 font-medium mt-1">
                {standard.title_hindi}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Link
              href={`/graph?standard=${encodeURIComponent(standard.is_number)}`}
              className="inline-flex items-center gap-1.5 bg-govNavy-900 hover:bg-govNavy-800 text-white px-4 py-2 rounded-lg text-xs font-semibold shadow transition-colors"
            >
              <Network className="w-4 h-4 text-govSaffron-500" />
              <span>Explore Citation Graph</span>
            </Link>
          </div>
        </div>

        {/* Currency Alert if Withdrawn or Superseded */}
        {(status === 'withdrawn' || status === 'superseded') && (
          <div className="bg-red-50 border-l-4 border-red-600 p-4 rounded-r text-xs sm:text-sm text-red-950">
            <p className="font-bold flex items-center gap-2 text-red-800">
              <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
              <span>OFFICIAL REGULATORY NOTICE: Standard is {status.toUpperCase()}</span>
            </p>
            <p className="mt-1 text-slate-700 leading-relaxed">
              This standard has been marked as <strong>{status.toUpperCase()}</strong> in official Bureau of Indian Standards
              records. {standard.superseded_by ? (
                <>It has been replaced by <strong className="text-red-900 underline">{standard.superseded_by}</strong>.</>
              ) : (
                'Please verify latest active revisions on the BIS portal before citing in procurement tenders.'
              )}
            </p>
          </div>
        )}

        {/* Tier 2 Catalogue Notice */}
        {!isEnriched && (
          <div className="bg-slate-50 border border-slate-200 p-4 rounded-lg text-xs sm:text-sm text-slate-700 flex items-start gap-3">
            <Info className="w-5 h-5 text-slate-500 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-slate-900">
                Catalogue metadata available. Detailed compliance dossier is not currently available for this standard.
              </p>
              <p className="text-slate-600 mt-1 leading-relaxed">
                This record represents a verified national standard published in the official BIS catalogue. Full normative
                references, technical scope, and specific certification schemes are populated for Tier 1 seed standards. Standard
                conformity tender specifications remain fully available below.
              </p>
            </div>
          </div>
        )}

        {/* Official Metadata Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
          <div className="bg-slate-50/70 border border-slate-200 p-3 rounded-lg">
            <span className="text-[11px] text-slate-500 font-medium block">Department / Division</span>
            <span className="text-xs font-bold text-slate-900 mt-0.5 block truncate" title={standard.department_name || standard.department || standard.division || 'BIS'}>
              {standard.department_name || standard.department || standard.division || 'BIS'}
            </span>
          </div>

          <div className="bg-slate-50/70 border border-slate-200 p-3 rounded-lg">
            <span className="text-[11px] text-slate-500 font-medium block">Aspect / Subject</span>
            <span className="text-xs font-bold text-slate-900 mt-0.5 block">
              {standard.aspect || 'Product Standard'}
            </span>
          </div>

          <div className="bg-slate-50/70 border border-slate-200 p-3 rounded-lg">
            <span className="text-[11px] text-slate-500 font-medium block">Publication Date</span>
            <span className="text-xs font-bold text-slate-900 mt-0.5 block">
              {standard.published_on || (standard.year ? `Year ${standard.year}` : 'Recorded')}
            </span>
          </div>

          <div className="bg-slate-50/70 border border-slate-200 p-3 rounded-lg">
            <span className="text-[11px] text-slate-500 font-medium block">Validity / Review Date</span>
            <span className="text-xs font-bold text-slate-900 mt-0.5 block">
              {standard.valid_upto || 'Current / Reaffirmed'}
            </span>
          </div>
        </div>
      </div>

      {/* TIER 1 ONLY: Rich Detail UI (Scope, Certification, Amendments, Allied References) */}
      {isEnriched && (
        <div className="space-y-6">
          {/* Scope Section */}
          {standard.scope && (
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
              <h4 className="text-base font-bold text-govNavy-900 flex items-center gap-2 mb-3">
                <BookOpen className="w-5 h-5 text-blue-700" />
                <span>Technical Scope & Application</span>
              </h4>
              <p className="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">
                {standard.scope}
              </p>
            </div>
          )}

          {/* Mandatory Certification Callout */}
          {standard.certification && (standard.certification.mandatory || standard.certification.scheme) && (() => {
            const scheme = (standard.certification.scheme || 'ISI').toUpperCase();
            const product = standard.certification.product || 'this item';
            return (
              <div className="bg-amber-50 border border-amber-300 rounded-xl p-5 shadow-sm text-xs sm:text-sm text-amber-950">
                <div className="flex items-start gap-3">
                  <ShieldCheck className="w-6 h-6 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-bold text-base text-amber-900">
                      MANDATORY CERTIFICATION REGIME: {standard.certification.scheme_label || `${scheme} Certification`}
                    </h4>
                    <p className="text-amber-900 mt-1 leading-relaxed">
                      Supply of {product} requires mandatory compliance with BIS regulations under applicable Quality Control Orders (QCO).
                      Bidders must submit active certification credentials (CM/L license, R-number, or HUID) with their tender proposals.
                    </p>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Amendments List */}
          {standard.amendments && standard.amendments.length > 0 && (
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
              <h4 className="text-base font-bold text-govNavy-900 flex items-center gap-2 mb-3">
                <FileText className="w-5 h-5 text-indigo-700" />
                <span>Gazetted Amendments ({standard.amendments.length})</span>
              </h4>
              <div className="flex flex-wrap gap-2">
                {standard.amendments.map((amdt) => (
                  <span
                    key={amdt.number}
                    className="inline-flex items-center gap-1.5 bg-blue-50 text-blue-900 border border-blue-200 px-3 py-1.5 rounded-lg text-xs font-mono font-medium"
                  >
                    <span>Amendment No. {amdt.number}</span>
                    {amdt.date && <span className="text-slate-500 font-sans">({amdt.date})</span>}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Allied Standards & Normative References */}
          {totalAlliedCount > 0 && (
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
              <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
                <h4 className="text-base font-bold text-govNavy-900 flex items-center gap-2">
                  <Layers className="w-5 h-5 text-govSaffron-500" />
                  <span>Normative References & Allied Taxonomy ({totalAlliedCount} verified)</span>
                </h4>
                <Link
                  href={`/graph?standard=${encodeURIComponent(standard.is_number)}`}
                  className="text-xs text-blue-700 hover:underline font-semibold"
                >
                  View in Graph →
                </Link>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {alliedRoles.map(([role, items]) => (
                  <div key={role} className="border border-slate-200 rounded-lg p-3 bg-slate-50/50">
                    <div className="flex items-center justify-between font-bold text-xs text-slate-800 mb-2">
                      <span>{role}</span>
                      <span className="bg-slate-200 text-slate-700 px-2 py-0.5 rounded text-[10px]">
                        {items.length}
                      </span>
                    </div>
                    <ul className="space-y-1.5 text-xs">
                      {items.map((it) => (
                        <li key={it.is_number} className="flex items-baseline justify-between gap-2">
                          <Link
                            href={`/standards/${encodeURIComponent(it.is_number)}`}
                            className="font-mono font-semibold text-blue-700 hover:underline"
                          >
                            {it.is_number}
                          </Link>
                          <span className="text-slate-600 truncate flex-1 text-right" title={it.title}>
                            {it.title}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tender Clause Section (Available for both Tier 1 and Tier 2) */}
      {standard.tender_clause && (
        <div className="bg-emerald-50/60 border border-emerald-200 rounded-xl p-6 shadow-sm space-y-3">
          <div className="flex items-center justify-between border-b border-emerald-200/60 pb-3">
            <div>
              <h4 className="text-base font-bold text-emerald-950 flex items-center gap-2">
                <FileText className="w-5 h-5 text-emerald-700" />
                <span>Legally Enforceable Tender Specification Clause</span>
              </h4>
              <p className="text-xs text-emerald-800 mt-0.5">
                Formatted for direct insertion into GeM tenders, NITs, and RFPs.
              </p>
            </div>
            <button
              type="button"
              onClick={copyClause}
              className="flex items-center gap-1.5 bg-white hover:bg-emerald-100 border border-emerald-300 text-emerald-900 px-3 py-1.5 rounded-lg text-xs font-semibold shadow-xs transition-colors"
            >
              {copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
              <span>{copied ? 'Copied!' : 'Copy Clause'}</span>
            </button>
          </div>

          <pre className="whitespace-pre-wrap font-mono text-xs text-emerald-950 leading-relaxed bg-white/80 p-4 rounded-lg border border-emerald-200/60">
            {standard.tender_clause}
          </pre>
        </div>
      )}
    </div>
  );
}
