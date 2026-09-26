// @vitest-environment jsdom
import { vi, describe, it, expect, beforeEach } from "vitest";

vi.mock("../api/client", () => ({
  api: {
    get: vi.fn(),
  },
}));

import { api } from "../api/client";
import {
  getStats,
  getSecurityStats,
  getSecurityConfig,
  getProjectStats,
  getDailyStats,
  getDxSyncStats,
} from "../api/stats";

const statsData = {
  total_documents: 42,
  pending_approvals: 3,
  active_users: 10,
  approved_this_month: 7,
  uploaded_this_week: 5,
  total_file_size_bytes: 1048576,
  by_type: { drawing: 20, spec: 22 },
  by_status: { approved: 35, pending: 7 },
};

const securityStatsData = {
  total_events: 100,
  login_success_total: 80,
  login_failed_total: 20,
  login_failed_30d: 5,
  provision_events_total: 3,
  active_sessions: 12,
};

const securityConfigData = {
  access_token_expire_minutes: 30,
  refresh_token_expire_days: 7,
  jwt_algorithm: "HS256",
  max_file_size_mb: 50,
  rbac_roles: ["admin", "manager", "engineer", "viewer"],
  audit_chain_enabled: true,
  audit_hash_algorithm: "sha256",
};

const projectStatsData = {
  period: 30,
  items: [
    {
      id: "p1",
      name: "Project A",
      code: "PRJ-001",
      total: 10,
      ok: 8,
      ng: 1,
      warn: 1,
    },
  ],
};

const dailyStatsData = {
  period: 30,
  series: [
    { date: "2026-06-01", count: 5 },
    { date: "2026-06-02", count: 3 },
  ],
};

const dxSyncStatsData = {
  total: 128,
  success: 126,
  error: 2,
  success_rate_total: 98.44,
  success_rate_30d: 99.2,
  recent_30d: { total: 125, success: 124, error: 1 },
  by_error_kind_30d: { rbac: 1 },
  monthly: [{ month: "2026-08", success: 124, error: 1 }],
};

describe("stats api client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("getStats calls GET /stats/ and returns data", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: statsData });
    const result = await getStats();
    expect(api.get).toHaveBeenCalledWith("/stats/");
    expect(result).toEqual(statsData);
  });

  it("getSecurityStats calls GET /stats/security and returns data", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: securityStatsData });
    const result = await getSecurityStats();
    expect(api.get).toHaveBeenCalledWith("/stats/security");
    expect(result).toEqual(securityStatsData);
  });

  it("getSecurityConfig calls GET /stats/security-config and returns data", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: securityConfigData });
    const result = await getSecurityConfig();
    expect(api.get).toHaveBeenCalledWith("/stats/security-config");
    expect(result).toEqual(securityConfigData);
  });

  it("getProjectStats calls GET /stats/projects with default period 30", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: projectStatsData });
    const result = await getProjectStats();
    expect(api.get).toHaveBeenCalledWith("/stats/projects", {
      params: { period: 30 },
    });
    expect(result).toEqual(projectStatsData);
  });

  it("getProjectStats forwards custom period parameter", async () => {
    const data = { ...projectStatsData, period: 7 };
    vi.mocked(api.get).mockResolvedValue({ data });
    const result = await getProjectStats(7);
    expect(api.get).toHaveBeenCalledWith("/stats/projects", {
      params: { period: 7 },
    });
    expect(result).toEqual(data);
  });

  it("getDailyStats calls GET /stats/daily with default period 30", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: dailyStatsData });
    const result = await getDailyStats();
    expect(api.get).toHaveBeenCalledWith("/stats/daily", {
      params: { period: 30 },
    });
    expect(result).toEqual(dailyStatsData);
  });

  it("getDxSyncStats calls GET /stats/dx-sync and returns data", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: dxSyncStatsData });
    const result = await getDxSyncStats();
    expect(api.get).toHaveBeenCalledWith("/stats/dx-sync");
    expect(result).toEqual(dxSyncStatsData);
  });

  it("getDailyStats forwards custom period parameter", async () => {
    const data = {
      period: 7,
      series: [{ date: "2026-06-15", count: 2 }],
    };
    vi.mocked(api.get).mockResolvedValue({ data });
    const result = await getDailyStats(7);
    expect(api.get).toHaveBeenCalledWith("/stats/daily", {
      params: { period: 7 },
    });
    expect(result).toEqual(data);
  });
});
