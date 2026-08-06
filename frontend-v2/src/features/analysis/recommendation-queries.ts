import { useQuery } from '@tanstack/react-query'
import { getDatasetRecommendations } from '../../api/v2-recommendations'

export const useDatasetRecommendations = (datasetId: string) =>
  useQuery({
    queryKey: ['analysis', 'recommendations', datasetId],
    queryFn: () => getDatasetRecommendations(datasetId),
    enabled: Boolean(datasetId),
  })
