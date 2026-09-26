import { useState, useCallback, useEffect, useMemo } from "react";
import { listDocuments, type DocumentResponse } from "../../../api/documents";
import {
  extractDocumentData,
  classifyDocument,
  type ExtractResponse,
  type ClassifyResponse,
} from "../../../api/ai";

interface ViewProps {
  onNavigate: (view: string) => void;
  onShowModal: (content: { title: string; body: string }) => void;
  onShowToast: (message: string, type?: "ok" | "warn" | "error") => void;
}

type TabKey = "check" | "extracted" | "meta";

type CheckStatus = "ok" | "ng" | "warn";

interface CheckItem {
  id: string;
  status: CheckStatus;
  title: string;
  detail: string;
  location: string;
}

const STATIC_CHECK_ITEMS: CheckItem[] = [
  {
    id: "c1",
    status: "ng",
    title: "縮尺表記の不一致",
    detail: "図面縮尺 1:200 だが属性値は 1:250",
    location: "p.1 右下 タイトル欄",
  },
  {
    id: "c2",
    status: "ng",
    title: "電子納品ファイル命名規則違反",
    detail: '得た値: "詳細図_rev04.pdf" 規定: "XXXXXX_D_00.pdf"',
    location: "ファイルメタデータ",
  },
  {
    id: "c3",
    status: "warn",
    title: "PDF/A 非準拠フォント埋込み",
    detail: "Type3 フォントが未埋込み (3箇所)",
    location: "p.1, p.3, p.5",
  },
  {
    id: "c4",
    status: "ok",
    title: "図面番号チェック",
    detail: "全ページの図面番号が連番で正常",
    location: "p.1〜p.8",
  },
  {
    id: "c5",
    status: "ok",
    title: "しおり構造チェック",
    detail: "電子納品要領に準拠した階層構造を確認",
    location: "ドキュメント全体",
  },
  {
    id: "c6",
    status: "ok",
    title: "作成者メタデータ",
    detail: "作成者・所属・作成日が正常に埋込まれています",
    location: "メタデータ",
  },
];

const TABS: { key: TabKey; label: string }[] = [
  { key: "check", label: "チェック" },
  { key: "extracted", label: "抽出データ" },
  { key: "meta", label: "メタ情報" },
];

const ZOOM_LEVELS = [50, 75, 100, 125, 150, 200];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function CheckIcon({ status }: { status: CheckStatus }) {
  return (
    <div className={`ep-check ${status}`} aria-hidden="true">
      {status === "ok" ? "✓" : status === "ng" ? "✕" : "!"}
    </div>
  );
}

export function ViewerView({
  onNavigate,
  onShowModal,
  onShowToast,
}: ViewProps) {
  const [activePage, setActivePage] = useState(1);
  const [zoomIndex, setZoomIndex] = useState(2);
  const [activeTab, setActiveTab] = useState<TabKey>("check");
  const [checkMode, setCheckMode] = useState(false);

  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [isLoadingDocs, setIsLoadingDocs] = useState(true);
  const [extractResult, setExtractResult] = useState<ExtractResponse | null>(
    null,
  );
  const [classifyResult, setClassifyResult] = useState<ClassifyResponse | null>(
    null,
  );
  const [isExtracting, setIsExtracting] = useState(false);
  const [isClassifying, setIsClassifying] = useState(false);

  useEffect(() => {
    listDocuments({ per_page: 50 })
      .then((docs) => {
        setDocuments(docs);
        if (docs.length > 0) {
          setSelectedDocId((cur) => cur ?? docs[0].id);
        }
      })
      .catch(() => {
        // Fall through to static demo mode silently
      })
      .finally(() => setIsLoadingDocs(false));
  }, []);

  const selectedDoc = useMemo(
    () => documents.find((d) => d.id === selectedDocId) ?? null,
    [documents, selectedDocId],
  );

  // No document selected → no pages. Used to default to a fabricated 8.
  const pageCount = selectedDoc?.page_count ?? 0;

  const zoom = ZOOM_LEVELS[zoomIndex];

  const handlePrevPage = useCallback(() => {
    setActivePage((p) => Math.max(1, p - 1));
  }, []);

  const handleNextPage = useCallback(() => {
    setActivePage((p) => Math.min(pageCount, p + 1));
  }, [pageCount]);

  const handleZoomOut = useCallback(() => {
    setZoomIndex((i) => Math.max(0, i - 1));
  }, []);

  const handleZoomIn = useCallback(() => {
    setZoomIndex((i) => Math.min(ZOOM_LEVELS.length - 1, i + 1));
  }, []);

  const handleCheckItemClick = useCallback(
    (item: CheckItem) => {
      const statusLabel =
        item.status === "ok" ? "正常" : item.status === "ng" ? "NG" : "警告";
      onShowModal({
        title: `[${statusLabel}] ${item.title}`,
        body: `詳細: ${item.detail}\n位置: ${item.location}`,
      });
    },
    [onShowModal],
  );

  const handleExtract = useCallback(async () => {
    if (!selectedDocId) return;
    setIsExtracting(true);
    try {
      const result = await extractDocumentData(selectedDocId);
      setExtractResult(result);
      setActiveTab("extracted");
      onShowToast("AI抽出が完了しました", "ok");
    } catch {
      onShowToast("AI抽出に失敗しました", "error");
    } finally {
      setIsExtracting(false);
    }
  }, [selectedDocId, onShowToast]);

  const handleClassify = useCallback(async () => {
    if (!selectedDocId) return;
    setIsClassifying(true);
    try {
      const result = await classifyDocument(selectedDocId);
      setClassifyResult(result);
      onShowToast("AI分類が完了しました", "ok");
    } catch {
      onShowToast("AI分類に失敗しました", "error");
    } finally {
      setIsClassifying(false);
    }
  }, [selectedDocId, onShowToast]);

  const handleDocChange = useCallback((id: string) => {
    setSelectedDocId(id);
    setActivePage(1);
    setExtractResult(null);
    setClassifyResult(null);
  }, []);

  const checkItems = STATIC_CHECK_ITEMS;
  const ngCount = checkItems.filter((c) => c.status === "ng").length;
  const warnCount = checkItems.filter((c) => c.status === "warn").length;
  const okCount = checkItems.filter((c) => c.status === "ok").length;

  const metaRows = selectedDoc
    ? [
        { label: "ファイル名", value: selectedDoc.filename },
        {
          label: "ファイルサイズ",
          value: formatFileSize(selectedDoc.file_size),
        },
        {
          label: "ページ数",
          value:
            selectedDoc.page_count != null
              ? String(selectedDoc.page_count)
              : "—",
        },
        { label: "種別", value: selectedDoc.document_type },
        { label: "ステータス", value: selectedDoc.status },
        { label: "PDF/A 準拠", value: selectedDoc.is_pdfa ? "準拠" : "非準拠" },
        {
          label: "タグ",
          value:
            selectedDoc.tags.length > 0 ? selectedDoc.tags.join(", ") : "—",
        },
        {
          label: "登録日時",
          value: new Date(selectedDoc.created_at).toLocaleString("ja-JP"),
        },
        {
          label: "更新日時",
          value: selectedDoc.updated_at
            ? new Date(selectedDoc.updated_at).toLocaleString("ja-JP")
            : "—",
        },
      ]
    : [
        // Previously showed a fabricated document (ファイル名 "県道○○号_詳細図_Rev04.dwg",
        // 218 MB, AutoCAD 2024, "OCR 処理: 完了 (日本語)") whenever no document was
        // selected — fake metadata presented as if it were a real file's
        // properties, including an OCR result this system cannot produce.
        { label: "状態", value: "選択された文書はありません" },
      ];

  const pageThumbs = Array.from({ length: pageCount }, (_, i) => i + 1);

  return (
    <div className="ep-viewer-shell">
      {/* Left: page thumbnails */}
      <div className="ep-vw-pages">
        {pageThumbs.map((num) => (
          <div
            key={num}
            className={`ep-pg-thumb${activePage === num ? " active" : ""}`}
            onClick={() => setActivePage(num)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter") setActivePage(num);
            }}
            aria-label={`ページ ${num}`}
            aria-pressed={activePage === num}
          >
            <div className="ep-pg-thumb-img">
              <span>p.{num}</span>
            </div>
            <div className="ep-pg-thumb-meta">
              <span>p.{num}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Center: canvas */}
      <div className="ep-vw-canvas">
        {/* Document selector */}
        <div
          style={{
            padding: "6px 12px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            background: "var(--surface-1)",
          }}
        >
          <span
            style={{ fontSize: "11px", color: "var(--muted)", flexShrink: 0 }}
          >
            📄 文書:
          </span>
          {isLoadingDocs ? (
            <span style={{ fontSize: "11px", color: "var(--muted)" }}>
              読み込み中…
            </span>
          ) : documents.length > 0 ? (
            <select
              style={{
                flex: 1,
                fontSize: "11px",
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: "4px",
                padding: "3px 6px",
                color: "var(--fg)",
              }}
              value={selectedDocId ?? ""}
              onChange={(e) => handleDocChange(e.target.value)}
            >
              {documents.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.title} ({doc.document_type})
                </option>
              ))}
            </select>
          ) : (
            <span style={{ fontSize: "11px", color: "var(--muted)" }}>
              デモモード — 文書未接続
            </span>
          )}
          {classifyResult && (
            <span
              style={{
                fontSize: "10px",
                fontFamily: "var(--font-mono)",
                color: "var(--accent)",
                flexShrink: 0,
              }}
            >
              [
              {classifyResult.drawing_type ??
                classifyResult.project_type ??
                "classified"}
              ]
            </span>
          )}
        </div>

        {/* Toolbar */}
        <div className="ep-vw-toolbar">
          <button
            className="ep-vw-tool-btn"
            type="button"
            onClick={handlePrevPage}
            disabled={activePage === 1}
            aria-label="前のページ"
          >
            ‹
          </button>
          <span className="pages-info">
            {activePage} / {pageCount}
          </span>
          <button
            className="ep-vw-tool-btn"
            type="button"
            onClick={handleNextPage}
            disabled={activePage === pageCount}
            aria-label="次のページ"
          >
            ›
          </button>
          <div className="div" />
          <button
            className="ep-vw-tool-btn"
            type="button"
            onClick={handleZoomOut}
            disabled={zoomIndex === 0}
            aria-label="ズームアウト"
          >
            −
          </button>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
              minWidth: "36px",
              textAlign: "center",
            }}
          >
            {zoom}%
          </span>
          <button
            className="ep-vw-tool-btn"
            type="button"
            onClick={handleZoomIn}
            disabled={zoomIndex === ZOOM_LEVELS.length - 1}
            aria-label="ズームイン"
          >
            +
          </button>
          <div className="div" />
          <button
            className={`ep-vw-tool-btn${checkMode ? " active" : ""}`}
            type="button"
            onClick={() => setCheckMode((v) => !v)}
            aria-label="チェックモード切替"
            aria-pressed={checkMode}
          >
            ✓
          </button>
          <div style={{ flex: 1 }} />
          <button
            className="ep-btn ep-btn-primary ep-btn-sm"
            type="button"
            onClick={() => onNavigate("workflow")}
          >
            ワークフローへ送る →
          </button>
        </div>

        {/* Page canvas */}
        <div
          style={{
            flex: 1,
            overflow: "auto",
            display: "flex",
            justifyContent: "center",
          }}
        >
          <div
            className="ep-vw-page"
            style={{
              transform: `scale(${zoom / 100})`,
              transformOrigin: "top center",
              marginTop: "16px",
            }}
          >
            <div
              style={{
                padding: "24px",
                height: "100%",
                display: "flex",
                flexDirection: "column",
                gap: "12px",
                fontSize: "9px",
                fontFamily: "var(--font-mono)",
                color: "#333",
              }}
            >
              <div
                style={{
                  borderBottom: "2px solid #333",
                  paddingBottom: "8px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div>
                  <div style={{ fontSize: "11px", fontWeight: 700 }}>
                    {selectedDoc?.title ?? "文書が選択されていません"}
                  </div>
                  <div style={{ color: "#666", marginTop: "2px" }}>
                    {selectedDoc?.document_type ?? "—"} · p.{activePage}
                    {selectedDoc && !selectedDoc.is_pdfa && (
                      <span style={{ color: "#c00", marginLeft: "8px" }}>
                        ⚠ PDF/A非準拠
                      </span>
                    )}
                  </div>
                </div>
                <div style={{ textAlign: "right", color: "#666" }}>
                  {selectedDoc ? (
                    <>
                      <div>{selectedDoc.status}</div>
                      <div>
                        {new Date(selectedDoc.created_at).toLocaleDateString(
                          "ja-JP",
                        )}
                      </div>
                    </>
                  ) : (
                    <>
                      <div>縮尺: 1:200</div>
                      <div>2024-06-12</div>
                    </>
                  )}
                </div>
              </div>
              <div
                style={{
                  flex: 1,
                  background:
                    "repeating-linear-gradient(0deg, #f5f5f5 0, #f5f5f5 1px, transparent 1px, transparent 20px), repeating-linear-gradient(90deg, #f5f5f5 0, #f5f5f5 1px, transparent 1px, transparent 20px)",
                  borderRadius: "2px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#aaa",
                }}
              >
                p.{activePage}
              </div>
              <table
                style={{
                  borderCollapse: "collapse",
                  fontSize: "8px",
                  width: "100%",
                }}
              >
                <thead>
                  <tr style={{ background: "#f0f0f0" }}>
                    <th
                      style={{
                        border: "1px solid #ccc",
                        padding: "3px 6px",
                        textAlign: "left",
                      }}
                    >
                      項目
                    </th>
                    <th
                      style={{
                        border: "1px solid #ccc",
                        padding: "3px 6px",
                        textAlign: "right",
                      }}
                    >
                      数量
                    </th>
                    <th
                      style={{
                        border: "1px solid #ccc",
                        padding: "3px 6px",
                        textAlign: "left",
                      }}
                    >
                      単位
                    </th>
                    <th
                      style={{
                        border: "1px solid #ccc",
                        padding: "3px 6px",
                        textAlign: "left",
                      }}
                    >
                      備考
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ["路盤工", "1,240", "m²", "砕石 t=200mm"],
                    ["表層工", "1,240", "m²", "As 混合物"],
                    ["側溝工", "185", "m", "L型側溝"],
                  ].map(([item, qty, unit, note]) => (
                    <tr key={item}>
                      <td
                        style={{ border: "1px solid #ccc", padding: "3px 6px" }}
                      >
                        {item}
                      </td>
                      <td
                        style={{
                          border: "1px solid #ccc",
                          padding: "3px 6px",
                          textAlign: "right",
                        }}
                      >
                        {qty}
                      </td>
                      <td
                        style={{ border: "1px solid #ccc", padding: "3px 6px" }}
                      >
                        {unit}
                      </td>
                      <td
                        style={{
                          border: "1px solid #ccc",
                          padding: "3px 6px",
                          color: "#666",
                        }}
                      >
                        {note}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {/* Right: extracted data panel */}
      <div className="ep-vw-extracted">
        <div className="ep-ve-tabs" role="tablist">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              className={`ep-ve-tab${activeTab === tab.key ? " active" : ""}`}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.key}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
              {tab.key === "check" && (
                <span style={{ marginLeft: "4px" }}>
                  {ngCount > 0 && (
                    <span
                      className="ep-pill ep-pill-ng"
                      style={{ padding: "0 4px", fontSize: "9px" }}
                    >
                      {ngCount}
                    </span>
                  )}
                  {warnCount > 0 && (
                    <span
                      className="ep-pill ep-pill-warn"
                      style={{
                        padding: "0 4px",
                        fontSize: "9px",
                        marginLeft: "2px",
                      }}
                    >
                      {warnCount}
                    </span>
                  )}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="ep-ve-content">
          {activeTab === "check" && (
            <div className="ep-ve-section">
              {/* Automatic drawing checks are not implemented yet: these items are
                  fixed samples and must not read as results for the open document. */}
              <div
                data-testid="check-demo-notice"
                style={{
                  fontSize: "11px",
                  color: "var(--muted)",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  marginBottom: "6px",
                }}
              >
                <span className="ep-pill ep-pill-warn">デモ</span>
                自動チェックは未実装です。以下は表示サンプルで、選択中の文書の検査結果ではありません
              </div>
              <h4>
                チェック結果（サンプル）
                <span style={{ display: "flex", gap: "4px" }}>
                  <span
                    style={{
                      color: "var(--danger)",
                      fontFamily: "var(--font-mono)",
                      fontSize: "10px",
                    }}
                  >
                    NG {ngCount}
                  </span>
                  <span
                    style={{
                      color: "var(--warn-fg)",
                      fontFamily: "var(--font-mono)",
                      fontSize: "10px",
                    }}
                  >
                    警告 {warnCount}
                  </span>
                  <span
                    style={{
                      color: "var(--success)",
                      fontFamily: "var(--font-mono)",
                      fontSize: "10px",
                    }}
                  >
                    OK {okCount}
                  </span>
                </span>
              </h4>
              {checkItems.map((item) => (
                <div
                  key={item.id}
                  className={`ep-check-item${item.status === "ng" ? " ng" : ""}`}
                  onClick={() => handleCheckItemClick(item)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleCheckItemClick(item);
                  }}
                >
                  <CheckIcon status={item.status} />
                  <div>
                    <div className="ep-ci-title">{item.title}</div>
                    <div className="ep-ci-detail">
                      {item.status === "ng" ? (
                        <span className="got">{item.detail}</span>
                      ) : (
                        item.detail
                      )}
                    </div>
                    <div className="ep-ci-loc">{item.location}</div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {activeTab === "extracted" && (
            <div className="ep-ve-section">
              <h4>
                抽出データ
                {extractResult && (
                  <span className="count">
                    {Object.keys(extractResult.data).length}
                  </span>
                )}
              </h4>
              {!extractResult ? (
                <div style={{ padding: "16px 0", textAlign: "center" }}>
                  <div
                    style={{
                      fontSize: "12px",
                      color: "var(--muted)",
                      marginBottom: "12px",
                    }}
                  >
                    {selectedDocId
                      ? "AI抽出を実行してデータを取得します"
                      : "デモ: 文書が選択されていません"}
                  </div>
                  {selectedDocId && (
                    <button
                      className="ep-btn ep-btn-primary ep-btn-sm"
                      type="button"
                      onClick={handleExtract}
                      disabled={isExtracting}
                      data-testid="extract-btn"
                    >
                      {isExtracting ? "抽出中…" : "AI抽出を実行"}
                    </button>
                  )}
                  {!selectedDocId && (
                    <div
                      style={{
                        fontSize: "11px",
                        color: "var(--muted)",
                        fontFamily: "var(--font-mono)",
                      }}
                    >
                      {[
                        { label: "工事名", value: "県道○○号線 道路改良工事" },
                        { label: "設計会社", value: "○○設計事務所" },
                        { label: "縮尺", value: "1:200" },
                        { label: "作成日", value: "2024-06-01" },
                      ].map((row) => (
                        <div
                          key={row.label}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            padding: "4px 0",
                            borderBottom: "1px solid var(--border)",
                          }}
                        >
                          <span style={{ color: "var(--muted)" }}>
                            {row.label}
                          </span>
                          <span style={{ color: "var(--fg)" }}>
                            {row.value}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <>
                  {Object.entries(extractResult.data)
                    .filter(([, v]) => v != null && v !== "")
                    .map(([key, value]) => (
                      <div
                        key={key}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          padding: "6px 0",
                          borderBottom: "1px solid var(--border)",
                          fontSize: "12px",
                        }}
                      >
                        <span style={{ color: "var(--muted)" }}>{key}</span>
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: "11px",
                            color: "var(--fg)",
                            textAlign: "right",
                            maxWidth: "60%",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {Array.isArray(value)
                            ? value.join(", ")
                            : String(value)}
                        </span>
                      </div>
                    ))}
                  <div
                    style={{ marginTop: "8px", display: "flex", gap: "6px" }}
                  >
                    <button
                      className="ep-btn ep-btn-secondary ep-btn-sm"
                      type="button"
                      onClick={handleClassify}
                      disabled={isClassifying}
                    >
                      {isClassifying ? "分類中…" : "🏷 AI分類"}
                    </button>
                    <button
                      className="ep-btn ep-btn-secondary ep-btn-sm"
                      type="button"
                      onClick={handleExtract}
                      disabled={isExtracting}
                    >
                      🔄 再抽出
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {activeTab === "meta" && (
            <div className="ep-ve-section">
              <h4>
                メタ情報
                <span className="count">{metaRows.length}</span>
              </h4>
              {metaRows.map((row) => (
                <div
                  key={row.label}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "6px 0",
                    borderBottom: "1px solid var(--border)",
                    fontSize: "12px",
                  }}
                >
                  <span style={{ color: "var(--muted)" }}>{row.label}</span>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "11px",
                      color:
                        row.value.includes("非準拠") ||
                        row.value.includes("警告")
                          ? "var(--danger)"
                          : "var(--fg)",
                      textAlign: "right",
                      maxWidth: "60%",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {row.value}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
