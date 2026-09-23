import './globals.css';
import type { Metadata } from 'next';
import Navbar from '@/components/Navbar';

export const metadata: Metadata = {
  title: 'IS Sarthi | मानक सारथी - AI Indian Standards Recommendation',
  description: 'AI-Powered Indian Standards (BIS) Recommendation, Allied Graph & Tender Compliance Audit',
  icons: {
    icon: '/assets/logo.png',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 flex flex-col text-slate-900 antialiased">
        <Navbar />
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {children}
        </main>
        <footer className="bg-white border-t border-slate-200 py-6 text-center text-xs text-slate-500">
          <div className="max-w-7xl mx-auto px-4">
            <p>
              🏛️ <strong>IS Sarthi (मानक सारथी)</strong> — Bureau of Indian Standards (BIS) Surface & Normative Traversal Engine.
            </p>
            <p className="mt-1 text-slate-400">
              Developed for Smart India Hackathon (SIH 2026) • WCAG 2.1 AA Compliant GovTech Interface
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
