import { useDeletion } from "../deletion";
import { Link } from "react-router-dom";
import { useState } from "react";
import { api, Page, Asset } from "../api";
import { useLoad } from "../hooks";
import { Heading, ErrorBox, Empty, Pager } from "../components";
export default function Assets() {
  const [page, setPage] = useState(1),
    [kind, setKind] = useState(""),
    [q, setQ] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [preview, setPreview] = useState<Asset | null>(null),
    [tags, setTags] = useState("");
  const load = useLoad(
    () =>
      api<Page<Asset>>(
        `assets/?page=${page}&kind=${kind}&q=${encodeURIComponent(q)}`,
      ),
    [page, kind, q],
  );
  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("tags", tags);
      await api("assets/", "POST", form);
      load.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const deletion = useDeletion(
    "assets",
    load.data?.results || [],
    () => {
      setPage(1);
      load.reload();
    },
    "素材文件也会删除；被引用的素材会保留。",
    `${page}:${kind}:${q}`,
  );
  return (
    <>
      <Heading
        title="素材库"
        subtitle="收集画面与声音，为每一个分镜找到灵感。"
      />
      <p>
        <Link className="button primary" to="/images">
          ＋ 文生图
        </Link>
      </p>
      <div
        className="upload-zone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (!busy) upload(e.dataTransfer.files[0]);
        }}
      >
        <div className="upload-symbol">↥</div>
        <h3>{busy ? "正在上传与校验…" : "拖入素材，或点击选择文件"}</h3>
        <p>JPEG / PNG / WebP ≤ 10MB · MP3 / WAV ≤ 20MB / 60秒</p>
        <input
          type="file"
          aria-label="上传素材"
          accept="image/jpeg,image/png,image/webp,audio/mpeg,audio/wav"
          disabled={busy}
          onChange={(e) => upload(e.target.files?.[0])}
        />
        <input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="可选标签：人物、场景、情绪…"
          aria-label="素材标签"
        />
      </div>
      <div className="toolbar">
        <input
          placeholder="搜索素材…"
          aria-label="搜索素材"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
        />
        <select
          aria-label="素材类型"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setPage(1);
          }}
        >
          <option value="">全部素材</option>
          <option value="image">图片</option>
          <option value="audio">音频</option>
        </select>
      </div>
      <ErrorBox error={error || load.error} />
      {deletion.toolbar}
      {load.data?.results.length ? (
        <div className="asset-grid">
          {load.data.results.map((a) => (
            <article className="asset-card" key={a.id}>
              <label className="select-item">
                {deletion.checkbox(a.id)}选择
              </label>
              <button className="asset-preview" onClick={() => setPreview(a)}>
                {a.kind === "image" ? (
                  <img loading="lazy" src={a.thumbnail_url} alt={a.name} />
                ) : (
                  <span>♫</span>
                )}
              </button>
              <div>
                <strong>{a.name}</strong>
                <p className="muted small">
                  {a.kind === "image" ? "图片" : "音频"} ·{" "}
                  {(a.size / 1024).toFixed(0)} KB · {a.tags || "未标记"}
                </p>
                <button
                  className="text danger"
                  onClick={async () => {
                    if (confirm("确认删除这个素材？"))
                      try {
                        await api(`assets/${a.id}/`, "DELETE");
                        load.reload();
                      } catch (e) {
                        setError((e as Error).message);
                      }
                  }}
                >
                  删除
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <Empty text="给故事准备第一份素材" />
      )}
      {load.data && (
        <Pager page={page} total={load.data.total} onChange={setPage} />
      )}{" "}
      {preview && (
        <div className="modal-backdrop" onClick={() => setPreview(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="close" onClick={() => setPreview(null)}>
              关闭 ×
            </button>
            <h3>{preview.name}</h3>
            {preview.kind === "image" ? (
              <img
                className="large-preview"
                src={preview.url}
                alt={preview.name}
              />
            ) : (
              <audio controls src={preview.url} />
            )}
          </div>
        </div>
      )}
    </>
  );
}
