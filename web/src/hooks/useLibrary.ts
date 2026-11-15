import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  deleteOpportunity,
  getLibrary,
  saveOpportunity,
  updateOpportunity,
} from '../api/endpoints'
import { queryKeys } from '../api/queryKeys'
import type { LibraryUpdatePayload, SavedStage } from '../api/types'

export function useLibrary() {
  return useQuery({
    queryKey: queryKeys.library,
    queryFn: getLibrary,
    retry: 1,
  })
}

export function useSaveOpportunity() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      runId,
      stage,
      notes,
    }: {
      runId: string
      stage?: SavedStage
      notes?: string
    }) => saveOpportunity(runId, stage, notes),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.library })
    },
  })
}

export function useUpdateOpportunity() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string
      payload: LibraryUpdatePayload
    }) => updateOpportunity(runId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.library })
    },
  })
}

export function useDeleteOpportunity() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => deleteOpportunity(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.library })
    },
  })
}
