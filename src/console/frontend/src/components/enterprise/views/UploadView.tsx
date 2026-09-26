import { useState, useCallback, useRef, useEffect } from "react";
import { uploadDocument, type Iso19650Metadata } from "../../../api/documents";
import { listProjects, type ProjectResponse } from "../../../api/projects";

interface ViewProps {
  onNavigate: (view: string) => void;
  onShowModal: (content: { title: string; body: string }) => void;
  onShowToast: (message: string, type?: "ok" | "warn" | "error") => void;
}

interface UploadFile {
  id: string;
  name: string;
  subLabel: string;
  type: string;
  size: string;
  progress: number;
  status: "done" | "uploading" | "warn";
}

interface ProcessingOption {
  id: string;
  label: string;
  description: string;
  value: boolean;
}

interface StandardChip {
  id: string;
  name: string;
  version: string;
  enabled: boolean;
}

const INITIAL_FILES: UploadFile[] = [];

const INITIAL_OPTIONS: ProcessingOption[] = [
  {
    id: "ocr",
    label: "OCR テキスト抽出",
    // Used to claim "Tesseract (jpn) で全ページをOCR処理". No OCR engine is a
    // dependency of this console (see api/ocr.py) and this toggle is never sent
    // to the server, so the description now states what actually exists.
    description: "画像PDFの文字認識（未実装・テキストレイヤ抽出のみ対応）",
    value: true,
  },
  {
    id: "table",
    label: "表データ抽出",
    description: "図面・仕様書内の表を構造化データに変換",
    value: true,
  },
  {
    id: "standard",
    label: "基準突合チェック",
    description: "国交省基準・設計図書と自動照合",
    value: true,
  },
  {
    id: "pdfa",
    label: "PDF/A 変換",
    description: "電子納品用 PDF/A-1b へ変換",
    value: false,
  },
  {
    id: "stamp",
    label: "電子印鑑 検出",
    description: "承認印・確認印の有無を検出",
    value: true,
  },
  {
    id: "meta",
    label: "メタデータ埋込み",
    description: "工事番号・作成者情報をメタデータに付与",
    value: true,
  },
  {
    id: "thumb",
    label: "サムネイル生成",
    description: "各ページのプレビュー画像を生成",
    value: false,
  },
];

const INITIAL_STANDARDS: StandardChip[] = [
  { id: "s1", name: "国交省電子納品要領", version: "R5版", enabled: true },
  { id: "s2", name: "道路設計要領", version: "2023年", enabled: true },
  { id: "s3", name: "橋梁設計標準", version: "H29版", enabled: false },
];

function fileIconBg(type: string): { bg: string; color: string } {
  switch (type) {
    case "PDF":
      return { bg: "var(--danger-soft)", color: "var(--danger)" };
    case "XLS":
      return { bg: "var(--success-soft)", color: "var(--success)" };
    case "DWG":
      return { bg: "var(--info-soft)", color: "var(--info)" };
    default:
      return { bg: "var(--surface-2)", color: "var(--muted)" };
  }
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${bytes}B`;
}

function guessType(filename: string): string {
  const ext = filename.split(".").pop()?.toUpperCase() ?? "";
  if (["XLS", "XLSX"].includes(ext)) return "XLS";
  if (["JPG", "JPEG", "PNG", "TIFF", "TIF"].includes(ext)) return "IMG";
  return ext || "FILE";
}

function guessDocumentType(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf") return "drawing";
  if (["xls", "xlsx"].includes(ext)) return "specification";
  if (["dwg", "dxf"].includes(ext)) return "drawing";
  return "other";
}

const ISO19650_FORM_OPTIONS = [
  { value: "", label: "選択なし" },
  { value: "DR", label: "DR - 図面" },
  { value: "SP", label: "SP - 仕様書" },
  { value: "CA", label: "CA - 計算書" },
  { value: "CO", label: "CO - 通信文書" },
  { value: "MS", label: "MS - 管理書類" },
  { value: "HS", label: "HS - 安全衛生" },
  { value: "PH", label: "PH - 写真" },
];

const ISO19650_DISCIPLINE_OPTIONS = [
  { value: "", label: "選択なし" },
  { value: "CI", label: "CI - 土木" },
  { value: "ST", label: "ST - 構造" },
  { value: "EL", label: "EL - 電気" },
  { value: "ME", label: "ME - 機械設備" },
  { value: "GE", label: "GE - 地質" },
  { value: "SU", label: "SU - 測量" },
  { value: "LA", label: "LA - 景観" },
  { value: "GN", label: "GN - 全般" },
];

export function UploadView({ onNavigate, onShowToast }: ViewProps) {
  const [files, setFiles] = useState<UploadFile[]>(INITIAL_FILES);
  const [options, setOptions] = useState<ProcessingOption[]>(INITIAL_OPTIONS);
  const [standards, setStandards] = useState<StandardChip[]>(INITIAL_STANDARDS);
  const [isDragging, setIsDragging] = useState(false);
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [iso19650, setIso19650] = useState<Iso19650Metadata>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listProjects()
      .then((data) => {
        setProjects(data);
        if (data.length > 0) setSelectedProjectId(data[0].id);
      })
      .catch(() => {
        /* no project list — user must enter manually */
      });
  }, []);

  const uploadFiles = useCallback(
    async (rawFiles: FileList | File[]) => {
      const fileArray = Array.from(rawFiles);
      if (fileArray.length === 0) return;

      const projectId = selectedProjectId;
      if (!projectId) {
        onShowToast("プロジェクトを選択してください", "warn");
        return;
      }

      const newEntries: UploadFile[] = fileArray.map((f) => ({
        id: `upload-${Date.now()}-${f.name}`,
        name: f.name,
        subLabel: `${guessType(f.name)} · ${formatSize(f.size)}`,
        type: guessType(f.name),
        size: formatSize(f.size),
        progress: 0,
        status: "uploading",
      }));
      setFiles((prev) => [
        ...prev.filter((f) => f.status !== "uploading"),
        ...newEntries,
      ]);

      await Promise.all(
        fileArray.map(async (f, idx) => {
          const entry = newEntries[idx];
          try {
            setFiles((prev) =>
              prev.map((pf) =>
                pf.id === entry.id ? { ...pf, progress: 30 } : pf,
              ),
            );
            await uploadDocument(
              projectId,
              f.name.replace(/\.[^/.]+$/, ""),
              guessDocumentType(f.name),
              f,
              iso19650,
            );
            setFiles((prev) =>
              prev.map((pf) =>
                pf.id === entry.id
                  ? { ...pf, progress: 100, status: "done" }
                  : pf,
              ),
            );
            onShowToast(`${f.name} をアップロードしました`, "ok");
          } catch {
            setFiles((prev) =>
              prev.map((pf) =>
                pf.id === entry.id
                  ? { ...pf, progress: 100, status: "warn" }
                  : pf,
              ),
            );
            onShowToast(`${f.name} のアップロードに失敗しました`, "error");
          }
        }),
      );
    },
    [selectedProjectId, iso19650, onShowToast],
  );

  const handleDropzoneClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files) {
        void uploadFiles(e.target.files);
        e.target.value = "";
      }
    },
    [uploadFiles],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      if (e.dataTransfer.files.length > 0) {
        void uploadFiles(e.dataTransfer.files);
      }
    },
    [uploadFiles],
  );

  const removeFile = useCallback((id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  }, []);

  const toggleOption = useCallback((id: string) => {
    setOptions((prev) =>
      prev.map((o) => (o.id === id ? { ...o, value: !o.value } : o)),
    );
  }, []);

  const toggleStandard = useCallback((id: string) => {
    setStandards((prev) =>
      prev.map((s) => (s.id === id ? { ...s, enabled: !s.enabled } : s)),
    );
  }, []);

  const enabledCount = options.filter((o) => o.value).length;
  const doneCount = files.filter((f) => f.status === "done").length;

  return (
    <div className="ep-upload-grid">
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.dwg,.dxf,.xlsx,.xls,.csv,.jpg,.jpeg,.png,.tiff,.tif,.zip"
        style={{ display: "none" }}
        onChange={handleFileInputChange}
        aria-hidden="true"
      />

      {/* Left: dropzone + file list */}
      <div>
        {/* Project selector */}
        {projects.length > 0 && (
          <div
            style={{
              marginBottom: "10px",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <label
              htmlFor="project-select"
              style={{
                fontSize: "12px",
                color: "var(--muted)",
                whiteSpace: "nowrap",
              }}
            >
              プロジェクト:
            </label>
            <select
              id="project-select"
              className="ep-select"
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              style={{ flex: 1 }}
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.code})
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Dropzone */}
        <div
          className={`ep-dropzone${isDragging ? " drag" : ""}`}
          onClick={handleDropzoneClick}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") handleDropzoneClick();
          }}
          aria-label="ファイルをドロップまたはクリックして選択"
        >
          <div className="ic">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M12 16V8m0 0-3 3m3-3 3 3"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d="M20 16.7A4 4 0 0 0 18 9h-1.26A7 7 0 1 0 4 15.7"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <h3>ファイルをドロップ</h3>
          <p>
            PDF・DWG・XLSX・画像ファイルをドラッグ&ドロップ
            <br />
            または<strong>クリックしてファイルを選択</strong>
          </p>
          <div className="file-types">
            対応形式: PDF · DWG · DXF · XLSX · CSV · JPG · PNG · TIFF · ZIP
          </div>
        </div>

        {/* File list */}
        <div className="ep-upload-list">
          <div className="ep-ul-head">
            <span />
            <span>ファイル名</span>
            <span>状態</span>
            <span>進捗</span>
            <span>サイズ</span>
            <span>処理</span>
            <span />
          </div>
          {files.map((file) => {
            const { bg, color } = fileIconBg(file.type);
            const progressClass =
              file.status === "done"
                ? "ep-progress done"
                : file.status === "warn"
                  ? "ep-progress warn"
                  : "ep-progress";
            return (
              <div key={file.id} className="ep-ul-row">
                <div className="ep-file-ic" style={{ background: bg, color }}>
                  {file.type.slice(0, 3)}
                </div>
                <div>
                  <div className="ep-fname">{file.name}</div>
                  <div className="ep-fsub">{file.subLabel}</div>
                </div>
                <div>
                  {file.status === "done" ? (
                    <span className="ep-pill ep-pill-ok">完了</span>
                  ) : file.status === "warn" ? (
                    <span className="ep-pill ep-pill-warn">警告</span>
                  ) : (
                    <span className="ep-pill ep-pill-info-2">転送中</span>
                  )}
                </div>
                <div className={progressClass}>
                  <div style={{ width: `${file.progress}%` }} />
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "11px",
                    color: "var(--muted)",
                  }}
                >
                  {file.size}
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "11px",
                    color: "var(--muted)",
                  }}
                >
                  {file.progress}%
                </div>
                <button
                  type="button"
                  onClick={() => removeFile(file.id)}
                  aria-label={`${file.name}を削除`}
                  style={{
                    width: "18px",
                    height: "18px",
                    display: "grid",
                    placeItems: "center",
                    color: "var(--muted)",
                    borderRadius: "3px",
                    cursor: "pointer",
                    background: "none",
                    border: "none",
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.color =
                      "var(--danger)";
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.color =
                      "var(--muted)";
                  }}
                >
                  ✕
                </button>
              </div>
            );
          })}
        </div>

        {/* Run bar */}
        <div className="ep-run-bar">
          <div className="summary">
            <strong>{files.length}</strong> ファイル ·{" "}
            <strong>{doneCount}</strong> 転送完了 ·{" "}
            <strong>{enabledCount}</strong> 処理オプション有効
          </div>
          <button
            className="ep-btn ep-btn-primary"
            type="button"
            onClick={() => {
              const doneFiles = files.filter((f) => f.status === "done");
              if (doneFiles.length === 0) {
                onShowToast("アップロード完了のファイルがありません", "warn");
                return;
              }
              onNavigate("viewer");
            }}
          >
            処理を実行 →
          </button>
        </div>
      </div>

      {/* Right: processing options */}
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <div className="ep-panel">
          <div className="ep-panel-head">
            <h3>処理オプション</h3>
            <span className="meta">
              {enabledCount}/{options.length} 有効
            </span>
          </div>
          <div className="ep-panel-body">
            {/* These toggles are local state only: uploadDocument() does not
                receive them, so nothing here changes what the server does. */}
            <p
              style={{ fontSize: 11, color: "var(--muted)", margin: "0 0 8px" }}
            >
              ⚠️
              これらの処理オプションは現在未実装です（サーバーへは送信されません）。
            </p>
            {options.map((opt) => (
              <div key={opt.id} className="ep-opt-row">
                <div className="lbl">
                  {opt.label}
                  <small>{opt.description}</small>
                </div>
                <div
                  className={`ep-toggle${opt.value ? " on" : ""}`}
                  role="switch"
                  aria-checked={opt.value}
                  tabIndex={0}
                  onClick={() => toggleOption(opt.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ")
                      toggleOption(opt.id);
                  }}
                  aria-label={opt.label}
                />
              </div>
            ))}
          </div>
        </div>

        <div className="ep-panel">
          <div className="ep-panel-head">
            <h3>適用基準</h3>
            <span className="meta">
              {standards.filter((s) => s.enabled).length} 選択中
            </span>
          </div>
          <div
            className="ep-panel-body"
            style={{ display: "flex", flexDirection: "column", gap: "6px" }}
          >
            {standards.map((std) => (
              <div
                key={std.id}
                className="ep-std-chip"
                onClick={() => toggleStandard(std.id)}
                role="checkbox"
                aria-checked={std.enabled}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ")
                    toggleStandard(std.id);
                }}
              >
                <div>
                  <span className="name">{std.name}</span>
                </div>
                <div
                  style={{ display: "flex", alignItems: "center", gap: "7px" }}
                >
                  <span className="ver">{std.version}</span>
                  <div
                    className={`ep-toggle${std.enabled ? " on" : ""}`}
                    style={{ pointerEvents: "none" }}
                    aria-hidden="true"
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ISO 19650 Metadata */}
        <div className="ep-panel">
          <div className="ep-panel-head">
            <h3>ISO 19650 メタデータ</h3>
            <span className="meta">電子納品 必須属性</span>
          </div>
          <div
            className="ep-panel-body"
            style={{ display: "flex", flexDirection: "column", gap: "8px" }}
          >
            <div>
              <label
                style={{
                  fontSize: "11px",
                  color: "var(--muted)",
                  display: "block",
                  marginBottom: "3px",
                }}
              >
                起源者コード (Originator)
              </label>
              <input
                className="ep-input"
                type="text"
                placeholder="例: ABC"
                maxLength={6}
                value={iso19650.originator ?? ""}
                onChange={(e) =>
                  setIso19650((prev) => ({
                    ...prev,
                    originator: e.target.value,
                  }))
                }
                aria-label="ISO 19650 起源者コード"
                style={{ width: "100%", textTransform: "uppercase" }}
              />
            </div>
            <div>
              <label
                style={{
                  fontSize: "11px",
                  color: "var(--muted)",
                  display: "block",
                  marginBottom: "3px",
                }}
              >
                機能分類 (Functional Breakdown)
              </label>
              <input
                className="ep-input"
                type="text"
                placeholder="例: 01-02-03"
                value={iso19650.functional_breakdown ?? ""}
                onChange={(e) =>
                  setIso19650((prev) => ({
                    ...prev,
                    functional_breakdown: e.target.value,
                  }))
                }
                aria-label="ISO 19650 機能分類"
                style={{ width: "100%" }}
              />
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "6px",
              }}
            >
              <div>
                <label
                  style={{
                    fontSize: "11px",
                    color: "var(--muted)",
                    display: "block",
                    marginBottom: "3px",
                  }}
                >
                  図書形式 (Form)
                </label>
                <select
                  className="ep-select"
                  value={iso19650.form ?? ""}
                  onChange={(e) =>
                    setIso19650((prev) => ({ ...prev, form: e.target.value }))
                  }
                  aria-label="ISO 19650 図書形式"
                  style={{ width: "100%" }}
                >
                  {ISO19650_FORM_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  style={{
                    fontSize: "11px",
                    color: "var(--muted)",
                    display: "block",
                    marginBottom: "3px",
                  }}
                >
                  工種 (Discipline)
                </label>
                <select
                  className="ep-select"
                  value={iso19650.discipline ?? ""}
                  onChange={(e) =>
                    setIso19650((prev) => ({
                      ...prev,
                      discipline: e.target.value,
                    }))
                  }
                  aria-label="ISO 19650 工種"
                  style={{ width: "100%" }}
                >
                  {ISO19650_DISCIPLINE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label
                style={{
                  fontSize: "11px",
                  color: "var(--muted)",
                  display: "block",
                  marginBottom: "3px",
                }}
              >
                連番 (Number)
              </label>
              <input
                className="ep-input"
                type="text"
                placeholder="例: 0001"
                maxLength={10}
                value={iso19650.number ?? ""}
                onChange={(e) =>
                  setIso19650((prev) => ({ ...prev, number: e.target.value }))
                }
                aria-label="ISO 19650 連番"
                style={{ width: "100%" }}
              />
            </div>
          </div>
        </div>

        <div className="ep-panel">
          <div className="ep-panel-head">
            <h3>出力設定</h3>
          </div>
          <div className="ep-panel-body">
            <div className="ep-opt-row">
              <div className="lbl">
                出力フォルダー
                <small>処理済みファイルの保存先</small>
              </div>
              <select className="ep-select" aria-label="出力フォルダー">
                <option>2024-038/図書</option>
                <option>2024-041/図書</option>
                <option>一時フォルダー</option>
              </select>
            </div>
            <div className="ep-opt-row">
              <div className="lbl">
                命名規則
                <small>ファイル名の自動整形ルール</small>
              </div>
              <select className="ep-select" aria-label="命名規則">
                <option>国交省標準</option>
                <option>社内標準</option>
                <option>元ファイル名</option>
              </select>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
