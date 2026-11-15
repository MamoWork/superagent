export type ProviderStatus =
  | 'ready'
  | 'needs_auth'
  | 'degraded'
  | 'disabled'
  | 'not_configured'

export type AuthKind = 'none' | 'browser' | 'api_key'
export type Capability = 'search' | 'read' | 'comments' | 'profile' | 'trends'
export type CostKind = 'free' | 'byo_key' | 'paid'
export type Verdict = 'build' | 'verify' | 'drop'
export type RunStatus = 'running' | 'completed' | 'partial' | 'failed'
export type SavedStage =
  | 'saved'
  | 'validating'
  | 'contacted'
  | 'replied'
  | 'won'
  | 'dropped'

export interface ProviderInfo {
  id: string
  name: string
  group: string
  capabilities: Capability[]
  auth: AuthKind
  status: ProviderStatus
  cost: CostKind
  rate_limit: Record<string, number> | null
  note: string | null
}

export interface ProviderHealth {
  id: string
  status: ProviderStatus
  detail: string
}

export interface ProviderErrorInfo {
  code: string
  message: string
  hint: string
  retry_after_seconds: number | null
}

export interface Signal {
  id: string
  provider_id: string
  source_type: string
  source_url: string
  title: string
  quote: string
  author_public: string | null
  published_at: string | null
  metrics: Record<string, unknown>
}

export interface Citation {
  signal_id: string
  source_url: string
  quote: string
  note: string
}

export interface DimensionScore {
  dimension_id: string
  name: string
  weight: number
  score: number
  weighted_points: number
  rationale: string
  citations: Citation[]
}

export interface NextAction {
  action: string
  owner: 'user' | 'ai'
  due_in_days: number | null
}

export interface RunStats {
  signal_count?: number
  domain_pack_name?: string
  time_range_days?: number | null
  limit_per_provider?: number
  provider_counts?: Record<string, number>
  provider_errors?: Record<string, ProviderErrorInfo>
  query?: string
}

export interface Run {
  id: string
  workspace_id: string
  domain_pack: string
  direction: string
  keywords: string[]
  provider_ids: string[]
  status: RunStatus
  stats: RunStats
  error: string | null
  created_at: string
  finished_at: string | null
  has_analysis: boolean
  signals: Signal[]
}

export type RunSummary = Omit<Run, 'signals'>

export interface OpportunityAnalysis {
  run_id: string
  domain_pack: string
  verdict: Verdict
  score: number
  one_liner: string
  thesis: string
  target_customer: string
  willingness_to_pay: string
  dimension_scores: DimensionScore[]
  next_actions: NextAction[]
  risks: string[]
  missing_information: string[]
  citations: Citation[]
  model: string
  created_at: string
}

export interface SavedOpportunity {
  run_id: string
  direction: string
  domain_pack: string
  title: string
  one_liner: string
  thesis: string
  score: number
  verdict: Verdict
  target_customer: string
  willingness_to_pay: string
  risks: string[]
  next_actions: NextAction[]
  dimension_scores: DimensionScore[]
  citations: Citation[]
  stage: SavedStage
  notes: string
  created_at: string
  updated_at: string
}

export interface Schedule {
  id: string
  workspace_id: string
  name: string
  domain_pack: string
  direction: string
  keywords: string[]
  provider_ids: string[]
  limit_per_provider: number
  time_range_days: number | null
  cron: string
  enabled: boolean
  last_run_id: string | null
  last_run_at: string | null
  last_error: string | null
  created_at: string
  next_run_at: string | null
}

export interface AIStatus {
  configured: boolean
  provider: string | null
  model: string | null
  base_url: string | null
  note: string
}

export interface AppInfo {
  desktop: boolean
  version: string
  db_path: string
  data_dir: string
  ui_available: boolean
}

export interface HealthInfo {
  ok: boolean
  service: string
  version: string
  providers: string[]
}

export interface ScoreDimensionSpec {
  id: string
  name: string
  weight: number
  description: string
}

export interface DomainPack {
  id: string
  name: string
  description: string
  query_hints: string[]
  scorecard: ScoreDimensionSpec[]
  output_schema: string
}

export interface RunCreatePayload {
  workspace_id?: string
  domain_pack: string
  direction: string
  keywords: string[]
  provider_ids: string[]
  limit_per_provider: number
  time_range_days: number | null
}

export interface ScheduleCreatePayload {
  workspace_id?: string
  name: string
  domain_pack: string
  direction: string
  keywords: string[]
  provider_ids: string[]
  limit_per_provider: number
  time_range_days: number | null
  cron: string
  enabled?: boolean
}

export type ScheduleUpdatePayload = Partial<
  Omit<ScheduleCreatePayload, 'workspace_id'>
>

export interface LibraryUpdatePayload {
  stage?: SavedStage
  notes?: string
}
