import { useQuery } from '@tanstack/react-query'
import { getAnalysis, getRun, getRuns } from '../api/endpoints'
import { queryKeys } from '../api/queryKeys'

export function useRuns(limit = 20) {
  return useQuery({
    queryKey: queryKeys.runs(limit),
    queryFn: () => getRuns(limit),
    retry: 1,
  })
}

export function useRun(runId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.run(runId || ''),
    queryFn: () => getRun(runId as string),
    enabled: Boolean(runId),
    retry: 1,
  })
}

export function useAnalysis(runId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.analysis(runId || ''),
    queryFn: () => getAnalysis(runId as string),
    enabled: Boolean(runId) && enabled,
    retry: 1,
  })
}
