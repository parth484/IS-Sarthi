'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Search, ShieldAlert, Network, BarChart3, Radio } from 'lucide-react';
import { fetchHealth } from '@/lib/api';

export default function Navbar() {
  const pathname = usePathname();
  const [telemetry, setTelemetry] = useState<{ status: string; standards_indexed: number; voice_enabled: boolean } | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setTelemetry)
      .catch(() => setTelemetry(null));
  }, []);

  const navItems = [
    { href: '/', label: 'Find Applicable Standards', icon: Search },
    { href: '/validator', label: 'Tender Spec Validator', icon: ShieldAlert },
    { href: '/graph', label: 'Dependency Graph Explorer', icon: Network },
    { href: '/analytics', label: 'Corpus & Division Analytics', icon: BarChart3 },
  ];

  return (
    <header className="w-full bg-govNavy-900 border-b border-slate-800 text-white shadow-md">
      {/* Top GovTech Banner */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-4 pb-4">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 bg-white/10 rounded-lg p-1 flex items-center justify-center border border-white/20 shadow-inner">
              <img
                src="/assets/logo.png"
                alt="IS Sarthi Logo"
                className="max-h-full max-w-full object-contain"
                onError={(e) => {
                  (e.target as HTMLImageElement).src = 'https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/Emblem_of_India.svg/200px-Emblem_of_India.svg.png';
                }}
              />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                  <span>🏛️ IS Sarthi</span>
                  <span className="text-govSaffron-500 font-normal">| मानक सारथी</span>
                </h1>
                <span className="hidden sm:inline-block bg-govSaffron-500/20 text-govSaffron-500 border border-govSaffron-500/40 text-xs px-2.5 py-0.5 rounded font-semibold uppercase tracking-wider">
                  GovTech Surface
                </span>
              </div>
              <p className="text-xs sm:text-sm text-slate-300 mt-1">
                AI-Powered Bureau of Indian Standards (BIS) Recommendation & Compliance Engine
              </p>
            </div>
          </div>

          {/* Telemetry Status Pill */}
          <div className="flex items-center gap-3">
            <div className="bg-slate-800/80 border border-slate-700/80 rounded-full px-3.5 py-1.5 flex items-center gap-2.5 text-xs text-slate-300">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span>
                <strong>{telemetry?.standards_indexed !== undefined ? telemetry.standards_indexed : '—'}</strong> Standards Indexed
              </span>
              <span className="text-slate-600">•</span>
              <span className="flex items-center gap-1 text-govSaffron-500">
                <Radio className="w-3 h-3 animate-pulse" />
                <span>Sarvam AI Active</span>
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Tabbed Navigation */}
      <nav className="bg-govNavy-950 border-t border-slate-800/60">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-1 sm:space-x-4 overflow-x-auto py-1 scrollbar-none">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-2 px-3 py-2.5 rounded-md text-sm font-medium transition-all whitespace-nowrap ${
                    isActive
                      ? 'bg-blue-600/30 text-white border-b-2 border-govSaffron-500 font-semibold'
                      : 'text-slate-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? 'text-govSaffron-500' : 'text-slate-400'}`} />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      </nav>
    </header>
  );
}
