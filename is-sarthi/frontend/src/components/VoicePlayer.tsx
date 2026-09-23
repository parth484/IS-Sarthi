'use client';

import React, { useState } from 'react';
import { Volume2, Loader2, Play, Pause } from 'lucide-react';
import { synthesizeSpeech } from '@/lib/api';

interface VoicePlayerProps {
  isNumber: string;
  title: string;
  status: string;
  justification?: string;
  supersededBy?: string | null;
}

const TTS_LANGUAGES = [
  { code: 'hi-IN', label: '🇮🇳 Hindi (हिन्दी)', native: 'हिन्दी' },
  { code: 'mr-IN', label: '🇮🇳 Marathi (मराठी)', native: 'मराठी' },
  { code: 'en-IN', label: '🇬🇧 English', native: 'English' },
  { code: 'te-IN', label: '🇮🇳 Telugu (తెలుగు)', native: 'తెలుగు' },
  { code: 'ta-IN', label: '🇮🇳 Tamil (தமிழ்)', native: 'தமிழ்' },
];

export default function VoicePlayer({
  isNumber,
  title,
  status,
  justification,
  supersededBy,
}: VoicePlayerProps) {
  const [lang, setLang] = useState('hi-IN');
  const [loading, setLoading] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [narrationText, setNarrationText] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);

  const handleGenerateAndPlay = async () => {
    setLoading(true);
    try {
      let promptText = `${isNumber}: ${title}. Status is ${status}.`;
      if (justification) promptText += ` Justification: ${justification}`;
      if (supersededBy) promptText += ` Note: this standard is superseded by ${supersededBy}.`;

      const res = await synthesizeSpeech(promptText, lang);
      setAudioUrl(res.audio_base64);
      setNarrationText(res.text);

      setTimeout(() => {
        if (audioRef.current) {
          audioRef.current.play();
          setIsPlaying(true);
        }
      }, 100);
    } catch (err: any) {
      alert(err.message || 'Speech generation failed');
    } finally {
      setLoading(false);
    }
  };

  const togglePlayback = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play();
      setIsPlaying(true);
    }
  };

  return (
    <div className="mt-3 pt-3 border-t border-slate-100">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2">
          <Volume2 className="w-4 h-4 text-govNavy-800" />
          <span className="font-semibold text-slate-700">Spoken Explanation:</span>
          <select
            value={lang}
            onChange={(e) => {
              setLang(e.target.value);
              setAudioUrl(null);
            }}
            disabled={loading}
            className="border border-slate-300 rounded px-2 py-0.5 text-xs bg-white text-slate-800 font-medium"
          >
            {TTS_LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          {!audioUrl ? (
            <button
              type="button"
              onClick={handleGenerateAndPlay}
              disabled={loading}
              className="flex items-center gap-1.5 bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-800 font-semibold px-2.5 py-1 rounded text-xs transition-colors"
            >
              {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3 h-3 text-blue-600" />}
              {loading ? 'Synthesizing with Sarvam AI...' : 'Play Voice Explanation'}
            </button>
          ) : (
            <button
              type="button"
              onClick={togglePlayback}
              className="flex items-center gap-1.5 bg-blue-50 border border-blue-200 text-blue-700 font-semibold px-2.5 py-1 rounded text-xs"
            >
              {isPlaying ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
              {isPlaying ? 'Pause Narration' : 'Resume Narration'}
            </button>
          )}
        </div>
      </div>

      {audioUrl && (
        <div className="mt-2.5 bg-blue-50/70 border border-blue-200/60 rounded-md p-2.5 text-xs">
          <audio
            ref={audioRef}
            src={audioUrl}
            onEnded={() => setIsPlaying(false)}
            onPause={() => setIsPlaying(false)}
            onPlay={() => setIsPlaying(true)}
            className="w-full h-8 mb-1.5"
            controls
          />
          {narrationText && (
            <p className="text-slate-700 italic border-l-2 border-blue-500 pl-2 mt-1">
              "{narrationText}"
            </p>
          )}
        </div>
      )}
    </div>
  );
}
