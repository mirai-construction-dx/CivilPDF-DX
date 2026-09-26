// @vitest-environment jsdom
import { vi, describe, it, expect, beforeEach } from "vitest";

vi.mock("../api/client", () => ({
  api: {
    get: vi.fn(),
  },
}));

import { api } from "../api/client";
import { downloadDocumentsCsv } from "../api/documents";
import { downloadAuditLogsCsv } from "../api/auditLogs";

describe("CSV export download helpers", () => {
  const createObjectURL = vi.fn(() => "blob:demo-url");
  const revokeObjectURL = vi.fn();
  const click = vi.fn();
  const remove = vi.fn();
  const appendChild = vi.fn();
  const fakeAnchor = { href: "", download: "", click, remove };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    });
    fakeAnchor.href = "";
    fakeAnchor.download = "";
    vi.spyOn(document, "createElement").mockReturnValue(
      fakeAnchor as unknown as HTMLAnchorElement,
    );
    vi.spyOn(document.body, "appendChild").mockImplementation(appendChild);
  });

  it("downloadDocumentsCsv downloads a blob with the server filename", async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: new Blob(["a,b"]),
      headers: {
        "content-disposition": 'attachment; filename="documents-2026.csv"',
      },
    });

    await downloadDocumentsCsv({ project_id: "p1" });

    expect(api.get).toHaveBeenCalledWith("/documents/export.csv", {
      params: { project_id: "p1" },
      responseType: "blob",
    });
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:demo-url");
  });

  it("downloadAuditLogsCsv forwards filters and falls back to a default name", async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: new Blob(["seq,action"]),
      headers: {},
    });

    await downloadAuditLogsCsv({ action: "auth.login_success" });

    expect(api.get).toHaveBeenCalledWith("/audit-logs/export.csv", {
      params: { action: "auth.login_success" },
      responseType: "blob",
    });
    expect(fakeAnchor.download).toBe("audit-logs.csv");
    expect(click).toHaveBeenCalledTimes(1);
  });
});
