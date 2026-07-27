import { useQuery } from '@tanstack/react-query'
import { listDatasetConversations } from '../../api/conversations'
import { datasetKeys } from '../datasets/queries'

export const useDatasetConversations = (fileId: string) =>
  useQuery({
    queryKey: datasetKeys.conversations(fileId),
    queryFn: () => listDatasetConversations(fileId),
    enabled: Boolean(fileId),
  })
