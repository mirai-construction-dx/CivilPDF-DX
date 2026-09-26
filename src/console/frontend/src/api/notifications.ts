import { api } from "./client";

export interface NotificationItem {
  id: string;
  notification_type: string;
  title: string;
  body: string | null;
  resource_type: string | null;
  resource_id: string | null;
  is_read: boolean;
  created_at: string | null;
}

export interface NotificationPage {
  items: NotificationItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export async function listNotifications(
  page = 1,
  perPage = 20,
): Promise<NotificationPage> {
  const res = await api.get<NotificationPage>("/notifications/", {
    params: { page, per_page: perPage },
  });
  return res.data;
}

export async function unreadCount(): Promise<number> {
  const res = await api.get<{ unread: number }>("/notifications/unread-count");
  return res.data.unread;
}

export async function markRead(id: string): Promise<NotificationItem> {
  const res = await api.post<NotificationItem>(`/notifications/${id}/read`);
  return res.data;
}

export async function markAllRead(): Promise<void> {
  await api.post("/notifications/read-all");
}
