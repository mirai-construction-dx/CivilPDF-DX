import { test, expect } from "@playwright/test";
import { setupApp } from "./helpers";

test.describe("App distribution page", () => {
  test("offers Windows installers only and marks macOS as pending", async ({
    page,
  }) => {
    await setupApp(page);
    await page.goto("/");
    await page
      .getByRole("button", { name: "アプリ配布", exact: true })
      .first()
      .click();

    await expect(page.getByText("インストーラー (.exe / NSIS)")).toBeVisible();
    await expect(page.getByText("インストーラー (.msi)")).toBeVisible();
    await expect(page.getByText(/\.dmg|\.deb|AppImage|\.rpm/)).toHaveCount(0);

    const mac = page.getByTestId("pending-macos");
    await expect(mac).toContainText("後日対応（ペンディング）");
    await mac.click();
    await expect(
      page.getByText("ステータス: 後日対応（ペンディング）"),
    ).toBeVisible();
  });

  test("shows a read-only distribution policy instead of toggles", async ({
    page,
  }) => {
    await setupApp(page);
    await page.goto("/");
    await page
      .getByRole("button", { name: "アプリ配布", exact: true })
      .first()
      .click();

    await expect(page.getByTestId("distribution-policy")).toContainText(
      "配布ポリシー",
    );
    await expect(page.getByRole("switch")).toHaveCount(0);
  });
});
