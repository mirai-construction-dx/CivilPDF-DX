import { type FC, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";
import {
  getM365Config,
  testM365Connection,
  type M365Config,
  type M365TestConnectionResult,
} from "../../../api/m365";

interface ViewProps {
  onNavigate: (view: string) => void;
  onShowModal: (content: { title: string; body: string }) => void;
  onShowToast: (message: string, type?: "ok" | "warn" | "error") => void;
}

// Derived connection state from the persisted m365_settings row. The backend
// stores tenant_id / client_id and the Fernet ciphertext of client_secret
// (exposed only as has_client_secret). "configured" means all credentials are
// present; only then can a token actually be acquired.
type ConnState = "connected" | "incomplete" | "disabled";

function deriveState(cfg: M365Config | undefined): ConnState {
  if (!cfg) return "disabled";
  const hasCreds =
    Boolean(cfg.tenant_id) && Boolean(cfg.client_id) && cfg.has_client_secret;
  if (!cfg.enabled) return "disabled";
  return hasCreds ? "connected" : "incomplete";
}

const STATE_PILL: Record<ConnState, string> = {
  connected: "ep-conn-status",
  incomplete: "ep-conn-status disc",
  disabled: "ep-conn-status disc",
};

const STATE_LABEL: Record<ConnState, string> = {
  connected: "設定済み",
  incomplete: "設定未完了",
  disabled: "無効",
};

const ROLE_LABEL: Record<string, string> = {
  admin: "管理者",
  manager: "マネージャー",
  editor: "編集者",
  viewer: "閲覧者",
};

function maskClientId(clientId: string): string {
  if (!clientId) return "—";
  if (clientId.length <= 8) return clientId;
  return `${clientId.slice(0, 8)}…`;
}

function buildConfigModalBody(cfg: M365Config): string {
  const lines = [
    "Microsoft 365 / Entra ID 接続設定",
    "",
    `テナントID: ${cfg.tenant_id || "（未設定）"}`,
    `クライアントID (アプリケーションID): ${cfg.client_id || "（未設定）"}`,
    `クライアントシークレット: ${cfg.has_client_secret ? "設定済み（暗号化保存・非表示）" : "未設定"}`,
    `連携: ${cfg.enabled ? "有効" : "無効"}`,
    `自動プロビジョニング: ${cfg.auto_provision ? "有効" : "無効"}`,
    `既定ロール: ${ROLE_LABEL[cfg.default_role] ?? cfg.default_role}`,
    "",
    "認証方式: Entra ID App登録 (OAuth2 client credentials)",
    "利用 API: Microsoft Graph (User.Read.All)",
    "",
    "※ クライアントシークレットは Fernet で暗号化して保存され、APIからは返却されません。",
    "※ 設定値の変更は API 経由 (PUT /m365/config) で行います。",
  ];
  return lines.join("\n");
}

export const M365View: FC<ViewProps> = ({ onShowModal, onShowToast }) => {
  const [testing, setTesting] = useState(false);

  const {
    data: config,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["m365", "config"],
    queryFn: getM365Config,
  });

  const state = deriveState(config);

  const handleTestConnection = async () => {
    setTesting(true);
    try {
      const result = await testM365Connection();
      onShowToast("Microsoft 365 接続テストに成功しました", "ok");
      onShowModal({
        title: "接続テスト結果 — 成功",
        body: [
          "Microsoft 365 / Entra ID への接続テストに成功しました。",
          "",
          `ステージ: ${result.stage}`,
          `詳細: ${result.detail}`,
          "",
          "アプリ登録の資格情報でアクセストークンを取得できました。",
        ].join("\n"),
      });
    } catch (err) {
      // The backend raises HTTPException whose JSON body is the diagnostic dict
      // (under `detail`). Surface the stage/detail honestly instead of a generic
      // failure message.
      let stage = "unknown";
      let detail = "接続テストに失敗しました";
      if (err instanceof AxiosError) {
        const data = err.response?.data as
          { detail?: M365TestConnectionResult | string } | undefined;
        const d = data?.detail;
        if (d && typeof d === "object") {
          stage = d.stage ?? stage;
          detail = d.detail ?? detail;
        } else if (typeof d === "string") {
          detail = d;
        } else if (err.message) {
          detail = err.message;
        }
      }
      onShowToast("Microsoft 365 接続テストに失敗しました", "error");
      onShowModal({
        title: "接続テスト結果 — 失敗",
        body: [
          "Microsoft 365 / Entra ID への接続テストに失敗しました。",
          "",
          `ステージ: ${stage}`,
          `詳細: ${detail}`,
          "",
          stage === "config"
            ? "テナントID・クライアントID・クライアントシークレットが正しく設定されているか確認してください。"
            : "アプリ登録の資格情報・権限 (Microsoft Graph) を確認してください。",
        ].join("\n"),
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Connection card — backed by GET /m365/config */}
      <div className="ep-m365-grid">
        <div className="ep-panel ep-conn">
          <div className="ep-conn-head">
            <div className="left">
              <div className="ep-conn-logo ent">EID</div>
              <div>
                <h4>Microsoft 365 / Entra ID</h4>
                <div className="ds">
                  Entra ID アプリ登録・Microsoft Graph ユーザー連携
                </div>
              </div>
            </div>
            {isLoading ? (
              <span className="ep-conn-status disc">確認中…</span>
            ) : isError ? (
              <span className="ep-conn-status disc">取得失敗</span>
            ) : (
              <span className={STATE_PILL[state]}>{STATE_LABEL[state]}</span>
            )}
          </div>

          {isError ? (
            <div className="ep-conn-rows">
              <div className="ep-conn-row">
                <span className="k">エラー</span>
                <span className="v">
                  {error instanceof Error
                    ? error.message
                    : "設定の取得に失敗しました"}
                </span>
              </div>
            </div>
          ) : (
            <div className="ep-conn-rows">
              <div className="ep-conn-row">
                <span className="k">テナントID</span>
                <span className="v">
                  {isLoading ? "—" : config?.tenant_id || "（未設定）"}
                </span>
              </div>
              <div className="ep-conn-row">
                <span className="k">クライアントID</span>
                <span className="v">
                  {isLoading ? "—" : maskClientId(config?.client_id ?? "")}
                </span>
              </div>
              <div className="ep-conn-row">
                <span className="k">シークレット</span>
                <span className="v">
                  {isLoading
                    ? "—"
                    : config?.has_client_secret
                      ? "設定済み"
                      : "未設定"}
                </span>
              </div>
              <div className="ep-conn-row">
                <span className="k">自動プロビジョニング</span>
                <span className="v">
                  {isLoading ? "—" : config?.auto_provision ? "有効" : "無効"}
                </span>
              </div>
              <div className="ep-conn-row">
                <span className="k">既定ロール</span>
                <span className="v">
                  {isLoading
                    ? "—"
                    : (ROLE_LABEL[config?.default_role ?? ""] ??
                      config?.default_role ??
                      "—")}
                </span>
              </div>
            </div>
          )}

          <div className="ep-conn-actions">
            {isError ? (
              <button
                className="ep-btn ep-btn-secondary ep-btn-sm"
                onClick={() => refetch()}
              >
                再取得
              </button>
            ) : (
              <>
                <button
                  className="ep-btn ep-btn-secondary ep-btn-sm"
                  onClick={handleTestConnection}
                  disabled={isLoading || testing}
                >
                  {testing ? "テスト中…" : "テスト接続"}
                </button>
                <button
                  className="ep-btn ep-btn-secondary ep-btn-sm"
                  onClick={() =>
                    config &&
                    onShowModal({
                      title: "Microsoft 365 — 設定",
                      body: buildConfigModalBody(config),
                    })
                  }
                  disabled={isLoading || !config}
                >
                  設定を表示
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Sync history — no backend endpoint exists yet. We deliberately do NOT
          show fabricated rows; the section is an honest "coming soon" notice. */}
      <div className="ep-panel">
        <div className="ep-panel-head">
          <h3>
            SharePoint 同期マッピング
            <span
              className="ep-pill ep-pill-muted"
              style={{ marginLeft: "8px" }}
            >
              今後提供
            </span>
          </h3>
        </div>
        <div className="ep-panel-body">
          <div
            style={{
              padding: "24px 16px",
              textAlign: "center",
              color: "var(--muted)",
              fontSize: "13px",
            }}
          >
            SharePoint / OneDrive の同期履歴は現在 API 未提供です。
            <br />
            Microsoft Graph ドライブ連携の実装後にこの画面で提供予定です。
          </div>
        </div>
      </div>
    </div>
  );
};
