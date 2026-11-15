import { DESKTOP_TOKEN, request } from './client'
import type {
  AIStatus,
  AppInfo,
  DomainPack,
  HealthInfo,
  LibraryUpdatePayload,
  OpportunityAnalysis,
  ProviderHealth,
  ProviderInfo,
  Run,
  RunCreatePayload,
  RunSummary,
  SavedOpportunity,
  SavedStage,
  Schedule,
  ScheduleCreatePayload,
  ScheduleUpdatePayload,
} from './types'

export const getHealth = () => request<HealthInfo>('/health', { timeoutMs: 5_000 })

export const getAppInfo = () => request<AppInfo>('/app/info', { timeoutMs: 5_000 })

export const getAIStatus = () => request<AIStatus>('/ai/status', { timeoutMs: 5_000 })

export const getProviders = () =>
  request<{ providers: ProviderInfo[] }>('/providers', { timeoutMs: 5_000 })

export const getProviderHealth = () =>
  request<{ providers: ProviderHealth[] }>('/providers/health', {
    timeoutMs: 15_000,
  })

export const getDomainPacks = () =>
  request<{ domain_packs: DomainPack[] }>('/domain-packs', { timeoutMs: 5_000 })

export const getRuns = (limit = 20) =>
  request<{ runs: RunSummary[] }>(`/runs?limit=${limit}`, { timeoutMs: 15_000 })

export const getRun = (runId: string) =>
  request<Run>(`/runs/${encodeURIComponent(runId)}`, { timeoutMs: 20_000 })

export const getAnalysis = (runId: string) =>
  request<OpportunityAnalysis>(`/runs/${encodeURIComponent(runId)}/analysis`, {
    timeoutMs: 20_000,
  })

export const createRun = (payload: RunCreatePayload) =>
  request<Run>('/runs', {
    method: 'POST',
    body: payload,
    timeoutMs: 240_000,
  })

export const analyzeRun = (runId: string) =>
  request<OpportunityAnalysis>(`/runs/${encodeURIComponent(runId)}/analyze`, {
    method: 'POST',
    body: {},
    timeoutMs: 300_000,
  })

export const getLibrary = () =>
  request<{ opportunities: SavedOpportunity[] }>('/library', {
    timeoutMs: 15_000,
  })

export const saveOpportunity = (
  runId: string,
  stage: SavedStage = 'saved',
  notes = '',
) =>
  request<SavedOpportunity>('/library', {
    method: 'POST',
    body: { run_id: runId, stage, notes },
    timeoutMs: 15_000,
  })

export const updateOpportunity = (
  runId: string,
  payload: LibraryUpdatePayload,
) =>
  request<SavedOpportunity>(`/library/${encodeURIComponent(runId)}`, {
    method: 'PATCH',
    body: payload,
    timeoutMs: 15_000,
  })

export const deleteOpportunity = (runId: string) =>
  request<null>(`/library/${encodeURIComponent(runId)}`, {
    method: 'DELETE',
    timeoutMs: 15_000,
  })

export const getSchedules = () =>
  request<{ schedules: Schedule[] }>('/schedules', { timeoutMs: 15_000 })

export const createSchedule = (payload: ScheduleCreatePayload) =>
  request<Schedule>('/schedules', {
    method: 'POST',
    body: payload,
    timeoutMs: 15_000,
  })

export const updateSchedule = (
  scheduleId: string,
  payload: ScheduleUpdatePayload,
) =>
  request<Schedule>(`/schedules/${encodeURIComponent(scheduleId)}`, {
    method: 'PATCH',
    body: payload,
    timeoutMs: 15_000,
  })

export const deleteSchedule = (scheduleId: string) =>
  request<null>(`/schedules/${encodeURIComponent(scheduleId)}`, {
    method: 'DELETE',
    timeoutMs: 15_000,
  })

export const runScheduleNow = (scheduleId: string) =>
  request<Run>(`/schedules/${encodeURIComponent(scheduleId)}/run`, {
    method: 'POST',
    timeoutMs: 240_000,
  })

export const shutdownApp = () =>
  request<{ ok: boolean }>('/app/shutdown', {
    method: 'POST',
    timeoutMs: 5_000,
    token: DESKTOP_TOKEN,
  })
