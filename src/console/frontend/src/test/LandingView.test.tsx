// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect } from "vitest";
import { LandingView } from "../components/enterprise/views/LandingView";

// LandingView is a static marketing/landing page by design (no API). The value
// worth testing is that its hero/pillar/footer CTAs route via onNavigate.
function makeProps() {
  return {
    onNavigate: vi.fn(),
    onShowModal: vi.fn(),
    onShowToast: vi.fn(),
  };
}

function renderView(props = makeProps()) {
  render(<LandingView {...props} />);
  return props;
}

describe("LandingView", () => {
  it("renders the hero and primary CTAs", () => {
    renderView();
    expect(
      screen.getByRole("button", { name: /アプリをDL/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /管理コンソールへ/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /PDFを解析する/ }),
    ).toBeInTheDocument();
  });

  it("routes the hero CTAs through onNavigate", async () => {
    const props = renderView();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /アプリをDL/ }));
    expect(props.onNavigate).toHaveBeenCalledWith("apps");

    await user.click(screen.getByRole("button", { name: /管理コンソールへ/ }));
    expect(props.onNavigate).toHaveBeenCalledWith("dashboard");

    await user.click(screen.getByRole("button", { name: /PDFを解析する/ }));
    expect(props.onNavigate).toHaveBeenCalledWith("upload");
  });

  it("shows capabilities instead of unmeasured usage numbers", () => {
    renderView();
    for (const fake of ["1,284", "248", "97.3%", "アクティブユーザー"]) {
      expect(screen.queryByText(fake)).toBeNull();
    }
    expect(screen.getByText("改ざん検知付き監査ログ")).toBeInTheDocument();
  });

  it("renders the feature pillars", () => {
    renderView();
    expect(screen.getByText("PDF業務基盤")).toBeInTheDocument();
    expect(screen.getByText("セキュリティ統制")).toBeInTheDocument();
    expect(screen.getByText("Microsoft365連携")).toBeInTheDocument();
  });

  it("navigates when a feature pillar is activated", async () => {
    const props = renderView();
    const user = userEvent.setup();

    // The security pillar card routes to the security view.
    await user.click(screen.getByText("セキュリティ統制"));
    expect(props.onNavigate).toHaveBeenCalledWith("security");
  });

  it("routes footer links through onNavigate", async () => {
    const props = renderView();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "アプリ配布" }));
    expect(props.onNavigate).toHaveBeenCalledWith("apps");
  });
});
