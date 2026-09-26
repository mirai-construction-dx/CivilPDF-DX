import { test, expect } from "@playwright/test";
import { setupApp, DOC_DRAWING, DOC_REPORT, PROJECT } from "./helpers";

// These tests drive the real, built application (vite preview) and verify that
// the Phase 8 features are reachable through the EnterpriseLayout shell — the
// regression that motivated wiring the functional pages into the shell.
test.describe("Phase 8 features reachable through the enterprise shell", () => {
  test("electronic timestamp modal opens and closes from 図書管理", async ({
    page,
  }) => {
    await setupApp(page, { documents: [DOC_DRAWING] });
    await page.goto("/");

    await page.getByRole("button", { name: "図書管理" }).click();
    await expect(page.getByText("橋梁設計図")).toBeVisible();

    await page.getByTitle(/電子タイムスタンプ/).click();
    await expect(page.getByText("🔏 電子タイムスタンプ")).toBeVisible();

    await page.getByRole("button", { name: "閉じる" }).last().click();
    await expect(page.getByText("🔏 電子タイムスタンプ")).toBeHidden();
  });

  test("electronic delivery modal opens and closes from プロジェクト", async ({
    page,
  }) => {
    await setupApp(page, { projects: [PROJECT] });
    await page.goto("/");

    await page.getByRole("button", { name: "プロジェクト" }).click();

    await page.getByRole("button", { name: /電子納品/ }).click();
    await expect(page.getByText("📦 電子納品パッケージ生成")).toBeVisible();
    await expect(page.getByText("納品可能")).toBeVisible();

    await page.getByRole("button", { name: "閉じる" }).last().click();
    await expect(page.getByText("📦 電子納品パッケージ生成")).toBeHidden();
  });

  test("document title filter narrows the list", async ({ page }) => {
    await setupApp(page, { documents: [DOC_DRAWING, DOC_REPORT] });
    await page.goto("/");

    await page.getByRole("button", { name: "図書管理" }).click();
    await expect(page.getByText("橋梁設計図")).toBeVisible();
    await expect(page.getByText("工事報告書")).toBeVisible();

    await page.getByLabel("タイトルで検索").fill("橋梁");
    await expect(page.getByText("橋梁設計図")).toBeVisible();
    await expect(page.getByText("工事報告書")).toBeHidden();
  });
});
