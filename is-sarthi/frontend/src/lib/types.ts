export interface Certification {
  scheme?: string;
  scheme_label?: string;
  mandatory?: boolean;
  product?: string;
}

export interface AlliedItem {
  is_number: string;
  title: string;
  status?: string;
  ref_type?: string;
  hop?: number;
  relevance?: number;
}

export interface Recommendation {
  is_number: string;
  title: string;
  status: 'current' | 'superseded' | 'withdrawn' | 'under_revision' | string;
  superseded_by?: string | null;
  latest_version: string;
  confidence: number;
  band: 'High' | 'Medium' | 'Low';
  justification: string;
  certification?: Certification | null;
  allied?: Record<string, AlliedItem[]>;
  tender_clause?: string;
  signals?: {
    dense_rank?: number | null;
    sparse_rank?: number | null;
  };
}

export interface RecommendResponse {
  query: string;
  state: 'ok' | 'low_confidence' | 'error';
  message?: string;
  recommendations: Recommendation[];
}

export interface AuditIssue {
  is_number: string;
  severity: 'high' | 'medium' | 'info';
  issue: string;
  action: string;
}

export interface SuggestedAddition {
  is_number: string;
  title?: string;
  role: string;
  referenced_by: string;
}

export interface ValidateResponse {
  cited: string[];
  issues: AuditIssue[];
  suggested_additions: SuggestedAddition[];
}

export interface StandardCatalogItem {
  is_number: string;
  title: string;
  division: string;
  year?: number;
  status: string;
  mandatory_qco: boolean;
  certification?: Certification;
}

export interface StandardsCatalogResponse {
  total: number;
  standards: StandardCatalogItem[];
}

export interface GraphNode {
  id: string;
  label: string;
  title: string;
  status: string;
  division: string;
  is_target: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  role: string;
}

export interface GraphResponse {
  target: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface TranscribeResponse {
  transcript: string;
  detected_language: string;
}

export interface SynthesizeResponse {
  text: string;
  language_code: string;
  audio_base64: string;
}
