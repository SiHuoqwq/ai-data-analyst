import { apiRequest } from './client'
import { parseDatasetRecommendations } from './v2-contracts'
import type { DatasetRecommendationResponse } from './v2-contracts'

export async function getDatasetRecommendations(datasetId: string): Promise<DatasetRecommendationResponse> {
  return parseDatasetRecommendations(
    await apiRequest<unknown>(
      `/api/v2/datasets/${encodeURIComponent(datasetId)}/recommendations`,
    ),
  )
}
