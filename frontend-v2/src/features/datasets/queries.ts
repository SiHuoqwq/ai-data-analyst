import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteDataset, getDataset, getDatasetPreview, listDatasets, uploadDataset } from '../../api/datasets'

export const datasetKeys = {
  all: ['datasets'] as const,
  detail: (id: string) => ['datasets', id] as const,
  preview: (id: string) => ['datasets', id, 'preview'] as const,
  conversations: (id: string) => ['datasets', id, 'conversations'] as const,
}

export const useDatasets = () => useQuery({ queryKey: datasetKeys.all, queryFn: listDatasets })
export const useDataset = (id: string) => useQuery({ queryKey: datasetKeys.detail(id), queryFn: () => getDataset(id), enabled: Boolean(id) })
export const useDatasetPreview = (id: string) =>
  useQuery({ queryKey: datasetKeys.preview(id), queryFn: () => getDatasetPreview(id), enabled: Boolean(id) })

export function useUploadDataset() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: uploadDataset,
    retry: false,
    onSuccess: (dataset) => {
      client.setQueryData(datasetKeys.detail(dataset.id), dataset)
      void client.invalidateQueries({ queryKey: datasetKeys.all })
    },
  })
}

export function useDeleteDataset() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: deleteDataset,
    retry: false,
    onSuccess: (_, fileId) => {
      client.removeQueries({ queryKey: datasetKeys.detail(fileId) })
      void client.invalidateQueries({ queryKey: datasetKeys.all })
    },
  })
}
