import { api } from "./client";

export interface ReleasePackage {
  id: string;
  platform: string;
  format: string;
  label: string;
  filename: string;
  version: string;
  size_label: string;
  sha256: string | null;
  download_path: string;
  available: boolean;
}

export interface ChannelInfo {
  id: string;
  label: string;
  version: string;
  release_date: string;
  description: string;
  user_count: number;
}

// Platforms announced but not yet distributed (e.g. macOS: 後日対応).
export interface PendingPlatform {
  platform: string;
  label: string;
  status: "pending";
  note: string;
}

export interface AppsReleasesResponse {
  stable_version: string;
  packages: ReleasePackage[];
  channels: ChannelInfo[];
  // Additive field; optional so older backends without it still type-check.
  pending_platforms?: PendingPlatform[];
}

export interface DownloadUrlResponse {
  url: string | null;
  sha256?: string | null;
  message?: string;
}

// Matches backend Channel = Literal["stable"] — only the stable channel exists.
export type ReleaseChannel = "stable";
// Matches backend NoteType = Literal["FEAT", "FIX", "SEC", "IMP", "NOTE"].
export type ReleaseNoteType = "FEAT" | "FIX" | "SEC" | "IMP" | "NOTE";

export interface ReleaseNoteItem {
  type: ReleaseNoteType;
  text: string;
}

export interface ReleaseNote {
  version: string;
  channel: ReleaseChannel;
  release_date: string;
  summary: string;
  items: ReleaseNoteItem[];
  highlights: string | null;
}

export interface ReleaseNotesResponse {
  notes: ReleaseNote[];
}

export interface BuildInfo {
  product: string;
  stable_version: string;
  build_number: string;
  git_commit: string | null;
  build_date: string | null;
  channel: string;
  runtime: string;
  supported_os: string[];
  min_supported_version: string;
}

export async function getAppsReleases(): Promise<AppsReleasesResponse> {
  const res = await api.get<AppsReleasesResponse>("/apps/releases");
  return res.data;
}

export async function getDownloadUrl(
  packageId: string,
): Promise<DownloadUrlResponse> {
  const res = await api.get<DownloadUrlResponse>(`/apps/download/${packageId}`);
  return res.data;
}

export async function getReleaseNotes(
  channel?: ReleaseChannel,
): Promise<ReleaseNotesResponse> {
  const res = await api.get<ReleaseNotesResponse>("/apps/release-notes", {
    params: channel ? { channel } : undefined,
  });
  return res.data;
}

export async function getBuildInfo(): Promise<BuildInfo> {
  const res = await api.get<BuildInfo>("/apps/build-info");
  return res.data;
}
