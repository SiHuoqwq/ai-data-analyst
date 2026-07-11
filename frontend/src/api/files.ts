import { apiClient } from './client';
import type { FileDetail, FileListItem, FilePreview } from '../types';

export async function uploadFile(file: File): Promise<FileDetail> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await apiClient.post<FileDetail>('/files/upload', form);
  return data;
}

export async function listFiles(): Promise<FileListItem[]> {
  const { data } = await apiClient.get<FileListItem[]>('/files');
  return data;
}

export async function getFileDetail(fileId: string): Promise<FileDetail> {
  const { data } = await apiClient.get<FileDetail>(`/files/${fileId}`);
  return data;
}

export async function getFilePreview(fileId: string, rows = 20): Promise<FilePreview> {
  const { data } = await apiClient.get<FilePreview>(`/files/${fileId}/preview`, {
    params: { rows },
  });
  return data;
}

export async function deleteFile(fileId: string): Promise<void> {
  await apiClient.delete(`/files/${fileId}`);
}
