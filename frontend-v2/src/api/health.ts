import { apiRequest } from './client'
import type { HealthResponse } from '../types/api'

export const getHealth = () => apiRequest<HealthResponse>('/health')
