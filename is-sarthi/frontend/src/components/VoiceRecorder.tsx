'use client';

import React, { useState, useRef } from 'react';
import { Mic, Square, Loader2, Globe } from 'lucide-react';
import { transcribeAudio } from '@/lib/api';

interface VoiceRecorderProps {
  onTranscribe: (text: string) => void;
}

const LANGUAGES = [
  { code: 'auto', label: '🌐 Auto-Detect' },
  { code: 'hi-IN', label: '🇮🇳 Hindi (हिन्दी)' },
  { code: 'mr-IN', label: '🇮🇳 Marathi (मराठी)' },
  { code: 'en-IN', label: '🇬🇧 English' },
  { code: 'te-IN', label: '🇮🇳 Telugu (తెలుగు)' },
  { code: 'ta-IN', label: '🇮🇳 Tamil (தமிழ்)' },
];

export default function VoiceRecorder({ onTranscribe }: VoiceRecorderProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [selectedLang, setSelectedLang] = useState('auto');
  const [isProcessing, setIsProcessing] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const startRecording = async () => {
    setErrorMsg(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];

      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        if (audioChunksRef.current.length === 0) return;

        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        setIsProcessing(true);
        try {
          const res = await transcribeAudio(audioBlob, selectedLang);
          if (res.transcript) {
            onTranscribe(res.transcript);
          } else {
            setErrorMsg('No distinct speech detected. Please speak clearly into the microphone.');
          }
        } catch (err: any) {
          setErrorMsg(err.message || 'Voice transcription failed.');
        } finally {
          setIsProcessing(false);
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
      setRecordingSeconds(0);

      timerIntervalRef.current = setInterval(() => {
        setRecordingSeconds((prev) => prev + 1);
      }, 1000);
    } catch (err: any) {
      setErrorMsg('Microphone access denied or unavailable in this browser.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
      }
    }
  };

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 sm:p-4 text-xs sm:text-sm">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-slate-500" />
          <span className="font-medium text-slate-700">Voice Language:</span>
          <select
            value={selectedLang}
            onChange={(e) => setSelectedLang(e.target.value)}
            disabled={isRecording || isProcessing}
            className="bg-white border border-slate-300 rounded px-2.5 py-1 text-xs text-slate-800 font-medium focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-3">
          {isRecording && (
            <span className="flex items-center gap-1.5 text-xs text-red-600 font-semibold animate-pulse">
              <span className="w-2 h-2 rounded-full bg-red-600"></span>
              Recording: {recordingSeconds}s
            </span>
          )}

          {isProcessing && (
            <span className="flex items-center gap-1.5 text-xs text-blue-600 font-medium">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Transcribing via Sarvam Saaras...
            </span>
          )}

          {!isRecording ? (
            <button
              type="button"
              onClick={startRecording}
              disabled={isProcessing}
              className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-md text-xs font-semibold shadow-sm transition-colors"
            >
              <Mic className="w-3.5 h-3.5" />
              Record Voice Requirement
            </button>
          ) : (
            <button
              type="button"
              onClick={stopRecording}
              className="flex items-center gap-1.5 bg-red-600 hover:bg-red-700 text-white px-3 py-1.5 rounded-md text-xs font-semibold shadow-sm transition-colors animate-pulse"
            >
              <Square className="w-3.5 h-3.5" />
              Stop & Transcribe
            </button>
          )}
        </div>
      </div>

      {errorMsg && (
        <p className="mt-2 text-xs text-red-600 font-medium bg-red-50 p-2 rounded border border-red-200">
          ⚠️ {errorMsg}
        </p>
      )}
    </div>
  );
}
