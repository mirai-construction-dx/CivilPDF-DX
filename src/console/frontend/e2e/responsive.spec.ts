import { test, expect, type Page } from "@playwright/test";
import { setupApp, STATS } from "./helpers";

// Responsive acceptance gate (2026-09-18).
//
// README promises 現場施工管理者 can check drawings "スマートフォン・タブレットで即確認",
// but the enterprise design system (src/styles/enterprise.css) contained no media
// queries at all, .ep-topbar-row never wrapped, and the only @media rules in the
// repo lived in src/App.css which nothing imports. These tests pin the actual
// requirement: the shell must not force horizontal scrolling on a phone or
// tablet. Measured, not asserted from CSS.

const VIEWPORTS = [
  { label: "mobile", width: 390, height: 844 },
  { label: "tablet", width: 768, height: 1024 },
] as const;

// Nav ids rendered in .ep-nav-groups (see EnterpriseLayout NAV_GROUPS).
const VIEWS = [
  { nav: null, label: "初期表示" },
  { nav: "図書管理", label: "図書管理" },
  { nav: "プロジェクト", label: "プロジェクト" },
  { nav: "ワークフロー", label: "ワークフロー" },
  { nav: "監査", label: "監査" },
  { nav: "ユーザー管理", label: "ユーザー管理" },
] as const;

interface OverflowReport {
  scrollWidth: number;
  innerWidth: number;
  offenders: string[];
}

/**
 * Report elements that stick out past the right edge (or are themselves wider
 * than the viewport), so a failure names the culprit instead of only a number.
 */
async function measureOverflow(page: Page): Promise<OverflowReport> {
  return page.evaluate(() => {
    const innerWidth = window.innerWidth;
    const scrollWidth = document.documentElement.scrollWidth;
    const offenders: string[] = [];
    if (scrollWidth > innerWidth + 1) {
      document.querySelectorAll<HTMLElement>("body *").forEach((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;
        if (rect.right > innerWidth + 1 || rect.width > innerWidth + 1) {
          const cls = (el.className || "")
            .toString()
            .trim()
            .split(/\s+/)
            .slice(0, 3)
            .join(".");
          offenders.push(
            `${el.tagName.toLowerCase()}${cls ? "." + cls : ""} w=${Math.round(rect.width)} right=${Math.round(rect.right)}`,
          );
        }
      });
    }
    return { scrollWidth, innerWidth, offenders: offenders.slice(0, 8) };
  });
}

for (const vp of VIEWPORTS) {
  test.describe(`レスポンシブ: ${vp.label} (${vp.width}x${vp.height})`, () => {
    for (const view of VIEWS) {
      test(`${view.label} で横スクロールが発生しない`, async ({ page }) => {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await setupApp(page);
        await page.goto("/");

        if (view.nav) {
          await page
            .locator(".ep-nav-groups button")
            .filter({ hasText: view.nav })
            .first()
            .click();
        }
        // Let layout settle (charts/tables render after the mocked fetch resolves).
        await page.waitForTimeout(400);

        const report = await measureOverflow(page);
        expect(
          report.scrollWidth,
          `横スクロールが発生: scrollWidth=${report.scrollWidth} > innerWidth=${report.innerWidth}\n` +
            `はみ出している要素:\n  ${report.offenders.join("\n  ")}`,
        ).toBeLessThanOrEqual(report.innerWidth + 1);
      });
    }

    test(`${vp.label} で主要コンテンツが操作可能な状態で表示される`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await setupApp(page);
      await page.goto("/");

      await expect(page.locator(".ep-root")).toBeVisible();
      await expect(page.locator(".ep-main")).toBeVisible();
      // The mocked document list must actually be reachable on a phone.
      await page
        .locator(".ep-nav-groups button")
        .filter({ hasText: "図書管理" })
        .first()
        .click();
      await expect(page.getByText("橋梁設計図").first()).toBeVisible();
    });

    test(`${vp.label} で承認待ちバッジが実データを表示する`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await setupApp(page);
      await page.goto("/");

      const workflowButton = page
        .locator(".ep-nav-groups button")
        .filter({ hasText: "ワークフロー" })
        .first();
      const badge = workflowButton.locator(".ep-nav-badge");
      // Value comes from /stats/ (3), not the previously hardcoded 7.
      await expect(badge).toHaveText(String(STATS.pending_approvals));
      // The count must be announced as words, not appended to the label.
      await expect(workflowButton).toHaveAttribute(
        "aria-label",
        new RegExp(`承認待ち ${STATS.pending_approvals} 件`),
      );
    });

    test(`${vp.label} で操作要素がタップできる大きさを持つ`, async ({
      page,
    }) => {
      // Measured, not assumed: "no horizontal scroll" is not the same as
      // "usable on a phone". WCAG 2.5.8 (AA) asks for a 24x24 CSS px minimum;
      // this records the controls that fall below it and names them.
      const MIN = 24;
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await setupApp(page);
      await page.goto("/");

      const offenders = await page.evaluate((min) => {
        const out: string[] = [];
        const selector =
          'button, a[href], [role="switch"], [role="tab"], [role="button"], select';
        document.querySelectorAll<HTMLElement>(selector).forEach((el) => {
          const rect = el.getBoundingClientRect();
          const style = getComputedStyle(el);
          if (style.display === "none" || style.visibility === "hidden") return;
          if (rect.width === 0 || rect.height === 0) return;
          if (rect.width < min || rect.height < min) {
            const cls = (el.className || "")
              .toString()
              .trim()
              .split(/\s+/)
              .slice(0, 2)
              .join(".");
            const label = (
              el.getAttribute("aria-label") ||
              el.textContent ||
              ""
            )
              .trim()
              .slice(0, 20);
            out.push(
              `${el.tagName.toLowerCase()}${cls ? "." + cls : ""} "${label}" ${Math.round(rect.width)}x${Math.round(rect.height)}`,
            );
          }
        });
        return out;
      }, MIN);

      expect(
        offenders,
        `${MIN}x${MIN}px 未満の操作要素:\n  ${offenders.join("\n  ")}`,
      ).toEqual([]);
    });
  });
}

test.describe("スマホ操作性（実測）", () => {
  test("主要ナビとアイコンボタンが 32px 以上である", async ({ page }) => {
    // The AA floor (24px) is checked above; on a site phone the shell's primary
    // controls are held to a stricter, measured target of 32px.
    await page.setViewportSize({ width: 390, height: 844 });
    await setupApp(page);
    await page.goto("/");

    const sizes = await page.evaluate(() => {
      const selector = ".ep-icon-btn, .ep-nav-item";
      const nodes = Array.from(
        document.querySelectorAll<HTMLElement>(selector),
      );
      return nodes.map((el) => {
        const rect = el.getBoundingClientRect();
        return {
          label: (el.getAttribute("aria-label") || el.textContent || "")
            .trim()
            .slice(0, 16),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          visible: rect.width > 0 && rect.height > 0,
        };
      });
    });

    const visible = sizes.filter((s) => s.visible);
    expect(
      visible.length,
      "操作要素が見つからない（テストが空振りしている）",
    ).toBeGreaterThan(0);

    const tooSmall = visible.filter((s) => s.width < 32 || s.height < 32);
    expect(
      tooSmall,
      `32px 未満の操作要素: ${JSON.stringify(tooSmall)}`,
    ).toEqual([]);
  });
});
