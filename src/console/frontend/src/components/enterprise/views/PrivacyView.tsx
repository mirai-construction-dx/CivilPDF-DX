import { type FC, useState, useEffect } from "react";
import { useAuthStore } from "../../../store/auth";
import {
  recordConsent,
  getConsentStatus,
  exportUserData,
  requestDeletion,
  type ConsentRecord,
  type DataExportResponse,
} from "../../../api/privacy";

interface ViewProps {
  onShowModal: (content: { title: string; body: string }) => void;
  onShowToast: (message: string, type?: "ok" | "warn" | "error") => void;
}

type Tab = "consent" | "export" | "delete";

const CONSENT_TYPES = [
  {
    key: "analytics",
    label: "アクセス解析",
    purpose: "サービス改善のための利用状況分析",
  },
  {
    key: "marketing",
    label: "マーケティング",
    purpose: "新機能・サービスのご案内",
  },
  {
    key: "third_party_sharing",
    label: "第三者提供",
    purpose: "パートナー企業との情報共有",
  },
];

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return iso.replace("T", " ").slice(0, 16);
}

export const PrivacyView: FC<ViewProps> = ({ onShowModal, onShowToast }) => {
  const { user } = useAuthStore();
  const [activeTab, setActiveTab] = useState<Tab>("consent");
  const [consentRecords, setConsentRecords] = useState<ConsentRecord[]>([]);
  const [exportData, setExportData] = useState<DataExportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);

  useEffect(() => {
    if (!user) return;
    getConsentStatus(user.id)
      .then(setConsentRecords)
      .catch(() => {
        /* not admin, or first load */
      });
  }, [user]);

  function latestConsent(type: string): ConsentRecord | undefined {
    return consentRecords
      .filter((r) => r.consent_type === type)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  }

  async function handleToggleConsent(type: string, currentGranted: boolean) {
    if (!user) return;
    setLoading(true);
    try {
      await recordConsent({
        consent_type: type,
        version: "1.0",
        granted: !currentGranted,
        source: "web",
      });
      const updated = await getConsentStatus(user.id);
      setConsentRecords(updated);
      onShowToast(
        !currentGranted ? "同意を記録しました" : "同意を取り消しました",
        !currentGranted ? "ok" : "warn",
      );
    } catch {
      onShowToast("操作に失敗しました", "error");
    } finally {
      setLoading(false);
    }
  }

  async function handleExport() {
    if (!user) return;
    setLoading(true);
    try {
      const data = await exportUserData(user.id);
      setExportData(data);
      onShowToast("データのエクスポートが完了しました", "ok");
    } catch {
      onShowToast("エクスポートに失敗しました", "error");
    } finally {
      setLoading(false);
    }
  }

  function downloadJson() {
    if (!exportData) return;
    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `privacy-export-${user?.id ?? "me"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleDeleteRequest() {
    if (!user) return;
    setLoading(true);
    try {
      const result = await requestDeletion(user.id);
      onShowModal({
        title: "削除リクエストを受け付けました",
        body: `ユーザーID: ${result.user_id}\n対象文書数: ${result.documents_marked} 件\n申請日時: ${result.deletion_requested_at}\n\n管理者が確認次第、物理削除処理が実行されます。\n監査ログは法的義務により保持されます。`,
      });
      setDeleteConfirm(false);
    } catch {
      onShowToast("削除リクエストに失敗しました", "error");
    } finally {
      setLoading(false);
    }
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "consent", label: "同意管理" },
    { id: "export", label: "データエクスポート" },
    { id: "delete", label: "削除リクエスト" },
  ];

  return (
    <div>
      {/* Header */}
      <div
        className="ep-stat-grid"
        style={{ gridTemplateColumns: "repeat(3, 1fr)", marginBottom: "16px" }}
      >
        <div className="ep-stat">
          <div className="lbl">対応法規</div>
          <div className="val" style={{ fontSize: "14px" }}>
            GDPR / CCPA
          </div>
          <div className="delta up">個人情報保護法</div>
        </div>
        <div className="ep-stat">
          <div className="lbl">同意レコード数</div>
          <div className="val">{consentRecords.length}</div>
          <div className="delta up">追記型管理</div>
        </div>
        <div className="ep-stat">
          <div className="lbl">削除権 (Art.17)</div>
          <div className="val" style={{ fontSize: "14px" }}>
            有効
          </div>
          <div className="delta up">論理削除 → 物理削除キュー</div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: "4px", marginBottom: "12px" }}>
        {tabs.map((t) => (
          <button
            key={t.id}
            className={`ep-filter-pill${activeTab === t.id ? " active" : ""}`}
            onClick={() => setActiveTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Consent Tab */}
      {activeTab === "consent" && (
        <div className="ep-panel">
          <div
            style={{
              padding: "12px 16px",
              borderBottom: "1px solid var(--border)",
              fontSize: "12px",
              color: "var(--muted)",
            }}
          >
            GDPR Art.7 準拠 —
            同意はいつでも取り消しできます。取り消しは新しいレコードとして記録されます。
          </div>
          <table className="ep-tbl">
            <thead>
              <tr>
                <th>同意種別</th>
                <th>目的</th>
                <th>現在の状態</th>
                <th>最終更新</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {CONSENT_TYPES.map(({ key, label, purpose }) => {
                const latest = latestConsent(key);
                const granted = latest?.granted ?? false;
                return (
                  <tr key={key}>
                    <td>
                      <strong>{label}</strong>
                    </td>
                    <td style={{ color: "var(--muted)", fontSize: "12px" }}>
                      {purpose}
                    </td>
                    <td>
                      <span
                        className={`ep-pill ${granted ? "ep-pill-ok" : "ep-pill-ng"}`}
                      >
                        <span className="dot" />
                        {granted ? "同意済み" : "未同意"}
                      </span>
                    </td>
                    <td style={{ color: "var(--muted)", fontSize: "12px" }}>
                      {formatDate(latest?.created_at ?? null)}
                    </td>
                    <td>
                      <button
                        className="ep-btn ep-btn-sm"
                        disabled={loading}
                        onClick={() => handleToggleConsent(key, granted)}
                        style={
                          granted
                            ? {
                                background: "var(--danger, #e53e3e)",
                                color: "#fff",
                              }
                            : {}
                        }
                      >
                        {granted ? "取り消す" : "同意する"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {consentRecords.length > 0 && (
            <>
              <div
                style={{
                  padding: "12px 16px 4px",
                  fontSize: "11px",
                  fontWeight: 600,
                  color: "var(--muted)",
                  letterSpacing: "0.05em",
                  textTransform: "uppercase",
                }}
              >
                同意履歴
              </div>
              <table className="ep-tbl">
                <thead>
                  <tr>
                    <th>種別</th>
                    <th>バージョン</th>
                    <th>状態</th>
                    <th>記録日時</th>
                    <th>ソース</th>
                  </tr>
                </thead>
                <tbody>
                  {[...consentRecords]
                    .sort((a, b) => b.created_at.localeCompare(a.created_at))
                    .slice(0, 10)
                    .map((r) => (
                      <tr key={r.id}>
                        <td>{r.consent_type}</td>
                        <td
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: "11px",
                          }}
                        >
                          {r.version}
                        </td>
                        <td>
                          <span
                            className={`ep-pill ${r.granted ? "ep-pill-ok" : "ep-pill-ng"}`}
                          >
                            <span className="dot" />
                            {r.granted ? "同意" : "取消"}
                          </span>
                        </td>
                        <td style={{ color: "var(--muted)", fontSize: "12px" }}>
                          {formatDate(r.created_at)}
                        </td>
                        <td style={{ color: "var(--muted)", fontSize: "12px" }}>
                          {r.source ?? "—"}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}

      {/* Export Tab */}
      {activeTab === "export" && (
        <div className="ep-panel" style={{ padding: "20px" }}>
          <h3 style={{ margin: "0 0 8px", fontSize: "14px" }}>
            データポータビリティ (GDPR Art.20)
          </h3>
          <p
            style={{
              color: "var(--muted)",
              fontSize: "12.5px",
              margin: "0 0 16px",
            }}
          >
            お客様のすべての個人データを JSON 形式でダウンロードできます。
            エクスポートには、アカウント情報・文書一覧・同意レコードが含まれます。
          </p>
          <div
            style={{
              display: "flex",
              gap: "8px",
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <button
              className="ep-btn"
              disabled={loading}
              onClick={handleExport}
            >
              {loading ? "取得中..." : "データを取得"}
            </button>
            {exportData && (
              <button className="ep-btn" onClick={downloadJson}>
                JSON ダウンロード
              </button>
            )}
          </div>

          {exportData && (
            <div style={{ marginTop: "16px" }}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "8px",
                  marginBottom: "12px",
                }}
              >
                <div className="ep-stat" style={{ padding: "10px 14px" }}>
                  <div className="lbl">文書数</div>
                  <div className="val">{exportData.documents.length}</div>
                </div>
                <div className="ep-stat" style={{ padding: "10px 14px" }}>
                  <div className="lbl">同意レコード数</div>
                  <div className="val">{exportData.consent_records.length}</div>
                </div>
              </div>
              <div
                style={{
                  background: "var(--bg-2, #f5f5f5)",
                  borderRadius: "6px",
                  padding: "12px",
                  fontSize: "11.5px",
                  fontFamily: "var(--font-mono)",
                  maxHeight: "240px",
                  overflow: "auto",
                  color: "var(--muted)",
                }}
              >
                <pre
                  style={{
                    margin: 0,
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-all",
                  }}
                >
                  {JSON.stringify(
                    {
                      user_id: exportData.user_id,
                      email: exportData.email,
                      role: exportData.role,
                      exported_at: exportData.exported_at,
                    },
                    null,
                    2,
                  )}
                </pre>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Delete Tab */}
      {activeTab === "delete" && (
        <div className="ep-panel" style={{ padding: "20px" }}>
          <h3
            style={{
              margin: "0 0 8px",
              fontSize: "14px",
              color: "var(--danger, #e53e3e)",
            }}
          >
            削除権の行使 (GDPR Art.17 / CCPA)
          </h3>
          <p
            style={{
              color: "var(--muted)",
              fontSize: "12.5px",
              margin: "0 0 8px",
            }}
          >
            アカウントおよび関連文書の削除をリクエストできます。
          </p>
          <ul
            style={{
              color: "var(--muted)",
              fontSize: "12px",
              margin: "0 0 16px",
              paddingLeft: "18px",
              lineHeight: "1.8",
            }}
          >
            <li>
              文書は「削除予約済み」状態になり、猶予期間後に物理削除されます
            </li>
            <li>監査ログは日本法の証跡保持義務により削除されません</li>
            <li>削除リクエストは管理者による確認が必要です</li>
          </ul>

          {!deleteConfirm ? (
            <button
              className="ep-btn"
              style={{ background: "var(--danger, #e53e3e)", color: "#fff" }}
              onClick={() => setDeleteConfirm(true)}
            >
              削除をリクエストする
            </button>
          ) : (
            <div
              style={{
                background: "rgba(229,62,62,0.08)",
                border: "1px solid var(--danger, #e53e3e)",
                borderRadius: "6px",
                padding: "14px",
                display: "flex",
                flexDirection: "column",
                gap: "10px",
              }}
            >
              <p
                style={{
                  margin: 0,
                  fontSize: "12.5px",
                  color: "var(--danger, #e53e3e)",
                  fontWeight: 600,
                }}
              >
                本当に削除リクエストを送信しますか？この操作は取り消せません。
              </p>
              <div style={{ display: "flex", gap: "8px" }}>
                <button
                  className="ep-btn"
                  style={{
                    background: "var(--danger, #e53e3e)",
                    color: "#fff",
                  }}
                  disabled={loading}
                  onClick={handleDeleteRequest}
                >
                  {loading ? "送信中..." : "削除リクエストを確定する"}
                </button>
                <button
                  className="ep-btn"
                  onClick={() => setDeleteConfirm(false)}
                >
                  キャンセル
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
