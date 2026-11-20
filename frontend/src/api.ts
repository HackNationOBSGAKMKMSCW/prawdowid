export interface Item {
  id: number;
  name: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  listItems: () => request<Item[]>('/items'),
  getItem: (id: string) => request<Item>(`/items/${id}`),
  createItem: (name: string) =>
    request<Item>('/items', { method: 'POST', body: JSON.stringify({ name }) }),
  deleteItem: (id: number) => request<void>(`/items/${id}`, { method: 'DELETE' }),
};
