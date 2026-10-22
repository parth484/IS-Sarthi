'use client';

import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  X,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  ShieldCheck,
  Building2,
  Sparkles,
  Copy,
  Check,
  FileText,
  Calendar,
  Layers,
  BookOpen,
  Info,
  Loader2,
} from 'lucide-react';
import { Recommendation, StandardDetail, AlliedItem } from '@/lib/types';
import { fetchStandardDetail } from '@/lib/api';

interface StandardDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  recommendation: Recommendation;
}

export default function StandardDetailModal({
  isOpen,
  onClose,
  recommendation: rec,
}: StandardDetailModalProps) {
  const [mounted, setMounted] = useState(false);
  const [detail, setDetail] = useState<StandardDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isEnriched = rec.tier === 'enriched' || rec.is_enriched === true;
  const status = (rec.status || 'current').toLowerCase();

  // If Tier 1 (enriched) and deep fields (like scope/normative_references) are not on rec, fetch full detail
  useEffect(() => {
    if (!isOpen) return;

    if (isEnriched && (!rec.scope || !detail)) {
      setLoadingDetail(true);
      fetchStandardDetail(rec.is_number)
        .then((data) => setDetail(data))
        .catch(() => {})
        .finally(() => setLoadingDetail(false));
    }
  }, [isOpen, isEnriched, rec.is_number, rec.scope]);

  // Keyboard accessibility: Escape key to close
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Lock background scroll when modal is open
  useEffect(() => {
    if (!isOpen) return;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [isOpen]);

  if (!isOpen || !mounted) return null;

  const tenderClause = detail?.tender_clause || rec.tender_clause;
  const copyClause = () => {
    if (tenderClause) {
      navigator.clipboard.writeText(tenderClause);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

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
            Withdrawn Standard
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

  const getTierBadge = () => {
    if (isEnriched) {
      return (
        <span
          title="Seed Enriched Dossier"
          className="inline-flex items-center gap-1.5 bg-blue-50 text-blue-800 border border-blue-200 px-2.5 py-0.5 rounded text-xs font-semibold"
        >
          <Sparkles className="w-3.5 h-3.5 text-blue-600 shrink-0" />
          <span>Seed Enriched Dossier</span>
        </span>
      );
    }
    return (
      <span
        title="Official BIS Catalogue"
        className="inline-flex items-center gap-1.5 bg-slate-100 text-slate-800 border border-slate-300 px-2.5 py-0.5 rounded text-xs font-semibold"
      >
        <Building2 className="w-3.5 h-3.5 text-slate-600 shrink-0" />
        <span>Official BIS Catalogue</span>
      </span>
    );
  };

  const certification = detail?.certification || rec.certification;
  const amendments = detail?.amendments || rec.amendments || [];
  const scope = detail?.scope || rec.scope;
  const normativeReferences = detail?.normative_references || [];
  const alliedByRole: Record<string, AlliedItem[]> =
    (detail?.allied_by_role as Record<string, AlliedItem[]>) ||
    (rec.allied as Record<string, AlliedItem[]>) ||
    {};
  const alliedEntries = Object.entries(alliedByRole).filter(
    ([_, items]) => Array.isArray(items) && items.length > 0
  );

  const modalContent = (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="standard-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-150"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-3xl bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[90vh] animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Top Header Bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/70 shrink-0">
          <div className="flex items-center gap-2">
            {isEnriched ? (
              <span className="text-xs font-bold uppercase tracking-wider text-blue-700 flex items-center gap-1.5">
                <Sparkles className="w-4 h-4 text-blue-600" />
                Enriched Compliance Dossier
              </span>
            ) : (
              <span className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                <Building2 className="w-4 h-4 text-slate-600" />
                Catalogue Metadata
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Modal Content */}
        <div className="overflow-y-auto px-6 py-5 space-y-5 flex-1">
          {/* Main Standard Header */}
          <div className="space-y-2 border-b border-slate-100 pb-4">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h2
                id="standard-modal-title"
                className="text-2xl font-black text-govNavy-900 tracking-tight"
              >
                {rec.is_number}
              </h2>
              {rec.latest_version && (
                <span className="text-xs bg-slate-100 text-slate-700 border border-slate-200 px-2 py-0.5 rounded font-mono font-medium">
                  Edition: {rec.latest_version}
                </span>
              )}
              {getTierBadge()}
              {getStatusBadge()}
            </div>

            <h3 className="text-base font-bold text-slate-800 leading-snug">
              {rec.title}
            </h3>

            {rec.title_hindi && (
              <div className="text-xs text-slate-500 font-medium">
                {rec.title_hindi}
              </div>
            )}
          </div>

          {/* Regulatory Warning if Withdrawn / Superseded */}
          {(status === 'withdrawn' || status === 'superseded') && (
            <div className="bg-red-50 border-l-4 border-red-600 p-4 rounded-r-lg text-xs sm:text-sm text-red-900 space-y-1">
              <p className="font-bold flex items-center gap-1.5 text-red-800">
                <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
                CRITICAL REGULATORY NOTICE: Outdated / Withdrawn Citation
              </p>
              <p className="text-slate-700 leading-relaxed">
                {rec.superseded_by
                  ? `This standard has been superseded by ${rec.superseded_by}. Citing it in public procurement or engineering NITs is legally vulnerable and non-compliant.`
                  : `This standard is marked as WITHDRAWN in the official BIS catalogue. Do not specify for active tenders or new engineering projects.`}
              </p>
            </div>
          )}

          {/* TIER 2: Official BIS Catalogue Metadata Grid */}
          {!isEnriched && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                {(rec.department_name || rec.department) && (
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                    <span className="text-slate-400 font-medium uppercase tracking-wider text-[10px] block">
                      Technical Department
                    </span>
                    <span className="font-bold text-slate-800 text-sm mt-0.5 block">
                      {rec.department_name || rec.department}
                    </span>
                  </div>
                )}
                {rec.aspect && (
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                    <span className="text-slate-400 font-medium uppercase tracking-wider text-[10px] block">
                      Aspect / Standard Type
                    </span>
                    <span className="font-bold text-slate-800 text-sm mt-0.5 block">
                      {rec.aspect}
                    </span>
                  </div>
                )}
                {rec.published_on && (
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                    <span className="text-slate-400 font-medium uppercase tracking-wider text-[10px] block">
                      Publication Date
                    </span>
                    <span className="font-bold text-slate-800 text-sm mt-0.5 block">
                      {rec.published_on}
                    </span>
                  </div>
                )}
                {rec.valid_upto && (
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                    <span className="text-slate-400 font-medium uppercase tracking-wider text-[10px] block">
                      Valid Upto / Review Date
                    </span>
                    <span className="font-bold text-slate-800 text-sm mt-0.5 block">
                      {rec.valid_upto}
                    </span>
                  </div>
                )}
              </div>

              {/* Tier 2 Official Catalogue Disclaimer */}
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-600 flex items-start gap-2.5">
                <Info className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
                <div>
                  <span className="font-bold text-slate-700 block">
                    Official BIS Catalogue Standard
                  </span>
                  <span>
                    Catalogue metadata available. Detailed compliance dossier is not currently available for this standard.
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* TIER 1: Enriched Dossier Sections */}
          {isEnriched && (
            <div className="space-y-4">
              {loadingDetail && !scope && (
                <div className="py-4 flex items-center justify-center gap-2 text-slate-500 text-xs">
                  <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                  <span>Loading enriched scope & normative network...</span>
                </div>
              )}

              {/* Technical Scope */}
              {scope && (
                <div className="space-y-1.5">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                    <BookOpen className="w-3.5 h-3.5 text-blue-600" />
                    Technical Scope & Requirements
                  </h4>
                  <p className="text-xs sm:text-sm text-slate-700 leading-relaxed bg-slate-50 p-3.5 rounded-lg border border-slate-200">
                    {scope}
                  </p>
                </div>
              )}

              {/* Certification & Quality Control Order */}
              {certification && (
                <div className="space-y-1.5">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                    <ShieldCheck className="w-3.5 h-3.5 text-blue-600" />
                    Certification & Quality Control Order
                  </h4>
                  <div className="bg-blue-50/70 border border-blue-200 rounded-lg p-3.5 text-xs text-slate-700 space-y-1.5">
                    <div className="flex items-center gap-2 flex-wrap font-semibold text-blue-900">
                      <span>Scheme: {certification.scheme || 'ISI Mark'}</span>
                      {certification.mandatory && (
                        <span className="bg-red-100 text-red-800 border border-red-200 px-2 py-0.5 rounded text-[11px] font-bold">
                          Mandatory QCO in Force
                        </span>
                      )}
                    </div>
                    {certification.scheme_label && (
                      <div className="text-slate-600">{certification.scheme_label}</div>
                    )}
                    {certification.details && (
                      <div className="text-slate-600">{certification.details}</div>
                    )}
                  </div>
                </div>
              )}

              {/* Normative References */}
              {normativeReferences.length > 0 && (
                <div className="space-y-1.5">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-blue-600" />
                    Normative References ({normativeReferences.length})
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {normativeReferences.map((ref) => (
                      <span
                        key={ref}
                        className="bg-white border border-slate-300 text-slate-800 font-mono text-xs px-2.5 py-1 rounded font-medium"
                      >
                        {ref}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Gazette Amendments */}
              {amendments.length > 0 && (
                <div className="space-y-1.5">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                    <span>📜</span>
                    Gazette Amendments ({amendments.length})
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {amendments.map((amdt) => (
                      <span
                        key={amdt.number}
                        className="bg-blue-50 text-blue-800 border border-blue-200 px-2.5 py-1 rounded text-xs font-mono font-medium"
                      >
                        Amdt {amdt.number} {amdt.date ? `(${amdt.date})` : ''}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Allied Standards & Normative Citation Network */}
              {alliedEntries.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                    <span>🔗</span>
                    Allied Standards & Normative Citation Network
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {alliedEntries.map(([role, items]) => (
                      <div
                        key={role}
                        className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs"
                      >
                        <span className="font-bold text-slate-800 block mb-1.5">
                          {role} ({items.length})
                        </span>
                        <ul className="space-y-1">
                          {items.slice(0, 4).map((it: any) => (
                            <li
                              key={it.is_number}
                              className="text-slate-700 flex items-baseline gap-1.5 truncate"
                              title={it.title}
                            >
                              <code className="bg-white border border-slate-200 px-1 py-0.5 rounded font-mono text-[10px] font-semibold text-govNavy-900 shrink-0">
                                {it.is_number}
                              </code>
                              <span className="truncate">{it.title}</span>
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

          {/* Formatted NIT / RFP Enforceable Clause */}
          {tenderClause && (
            <div className="space-y-2 pt-2 border-t border-slate-100">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-800 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-emerald-600" />
                  NIT / RFP Enforceable Tender Clause
                </h4>
                <button
                  type="button"
                  onClick={copyClause}
                  className="flex items-center gap-1 bg-emerald-50 hover:bg-emerald-100 border border-emerald-300 text-emerald-800 px-2.5 py-1 rounded text-xs font-semibold transition-colors cursor-pointer"
                >
                  {copied ? (
                    <Check className="w-3.5 h-3.5 text-emerald-600" />
                  ) : (
                    <Copy className="w-3.5 h-3.5 text-emerald-600" />
                  )}
                  <span>{copied ? 'Copied!' : 'Copy Clause'}</span>
                </button>
              </div>
              <pre className="whitespace-pre-wrap font-mono text-[11px] text-emerald-950 leading-relaxed bg-emerald-50/50 p-3.5 rounded-lg border border-emerald-200/60">
                {tenderClause}
              </pre>
            </div>
          )}
        </div>

        {/* Modal Bottom Footer Bar */}
        <div className="px-6 py-3.5 bg-slate-50 border-t border-slate-200 flex items-center justify-between shrink-0 text-xs">
          <div className="text-slate-500 font-medium">
            {isEnriched
              ? 'Seed Enriched Dossier • SIH 2026 GovTech Interface'
              : 'Official BIS Published Standards Catalogue (Tier 2)'}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-800 font-semibold rounded-lg text-xs transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
}
