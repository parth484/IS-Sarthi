import {
  RecommendResponse,
  ValidateResponse,
  StandardsCatalogResponse,
  GraphResponse,
  TranscribeResponse,
  SynthesizeResponse,
  ExtractPdfResponse,
} from './types';

const API_BASE = '/api';

export async function fetchHealth(): Promise<{ status: string; standards_indexed: number; voice_enabled: boolean }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Failed to fetch API health');
  return res.json();
}

export async function recommendStandards(
  query: string,
  top_k: number = 5,
  division?: string
): Promise<RecommendResponse> {
  const res = await fetch(`${API_BASE}/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k, division: division === 'All Divisions' ? null : division }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Recommendation failed' }));
    throw new Error(err.detail || 'Recommendation request failed');
  }
  return res.json();
}

export async function validateSpecification(spec_text: string): Promise<ValidateResponse> {
  const res = await fetch(`${API_BASE}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ spec_text }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Validation failed' }));
    throw new Error(err.detail || 'Validation request failed');
  }
  return res.json();
}

export async function fetchStandards(division?: string, search?: string): Promise<StandardsCatalogResponse> {
  const params = new URLSearchParams();
  if (division && division !== 'All') params.append('division', division);
  if (search) params.append('search', search);

  const res = await fetch(`${API_BASE}/standards?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to load standards catalog');
  return res.json();
}

export async function fetchStandardGraph(is_number: string, depth: number = 1): Promise<GraphResponse> {
  const encoded = encodeURIComponent(is_number);
  const res = await fetch(`${API_BASE}/standards/${encoded}/graph?depth=${depth}`);
  if (!res.ok) throw new Error(`Failed to load dependency graph for ${is_number}`);
  return res.json();
}

export async function transcribeAudio(audioBlob: Blob, language_code: string = 'auto'): Promise<TranscribeResponse> {
  const formData = new FormData();
  formData.append('file', audioBlob, 'recording.wav');
  formData.append('language_code', language_code);

  const res = await fetch(`${API_BASE}/speech/transcribe`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Transcription failed' }));
    throw new Error(err.detail || 'Speech transcription failed');
  }
  return res.json();
}

export async function synthesizeSpeech(text: string, language_code: string = 'hi-IN'): Promise<SynthesizeResponse> {
  const res = await fetch(`${API_BASE}/speech/synthesize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, language_code }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Speech synthesis failed' }));
    throw new Error(err.detail || 'Speech synthesis failed');
  }
  return res.json();
}

export async function submitFeedback(is_number: string, verdict: 'relevant' | 'irrelevant', query?: string) {
  const res = await fetch(`${API_BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_number, verdict, query }),
  });
  return res.ok;
}

export async function extractPdfText(file: File): Promise<ExtractPdfResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/extract-pdf`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to extract text from PDF' }));
    throw new Error(err.detail || 'Failed to extract text from PDF');
  }

  return res.json();
}
