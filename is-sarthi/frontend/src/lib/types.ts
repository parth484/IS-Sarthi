export type CertificationScheme = 'ISI' | 'CRS' | 'Hallmarking' | string;

export interface Certification {
  scheme?: CertificationScheme;
  scheme_label?: string;
  mandatory?: boolean;
  product?: string;
  details?: string;
}

export interface Amendment {
  number: string;
  date?: string | null;
}

export type AlliedRole =
  | 'Test method'
  | 'Related product'
  | 'Terminology'
  | 'Safety'
  | 'Installation'
  | 'Sampling'
  | 'Dimensions'
  | string;

export interface AlliedItem {
  is_number: string;
  title: string;
  status?: string;
  ref_type?: string;
  role?: AlliedRole;
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
  amendments?: Amendment[];
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
  normalized_query?: string;
  detected_language?: string;
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

export interface ExtractDocumentResponse {
  text: string;
  filename: string;
  character_count: number;
  format?: string;
}

export type ExtractPdfResponse = ExtractDocumentResponse;

export interface ProcurementTender {
  tender_id: string;
  title: string;
  portal?: string;
  organization?: string;
  reference_number?: string;
  closing_date?: string | null;
  category?: string;
  raw_specification?: string;
  line_items?: Array<{ item: string; quantity: string } | string>;
  metadata?: Record<string, any>;
}

export interface ProcurementIngestResponse {
  tender: {
    tender_id: string;
    title: string;
    portal: string;
    organization: string;
    normalized_query: string;
    technical_parameters?: Record<string, any>;
    cited_standards?: string[];
    raw_specification?: string;
  };
  recommendations: Recommendation[];
  state: 'ok' | 'low_confidence' | 'error';
  query_used: string;
  validation?: ValidateResponse | null;
}
