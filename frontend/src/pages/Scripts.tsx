import { useDeletion } from "../deletion";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Page, Script, key } from "../api";
import { useLoad } from "../hooks";
import { Heading, ErrorBox, Empty, Pager } from "../components";
export default function Scripts() {
  const [page, setPage] = useState(1),
    [q, setQ] = useState(""),
    [error, setError] = useState(""),
    [topic, setTopic] = useState(""),
    [style, setStyle] = useState("甜宠"),
    [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const load = useLoad(
    () => api<Page<Script>>(`scripts/?page=${page}&q=${encodeURIComponent(q)}`),
    [page, q],
  );
  const deletion = useDeletion(
    "scripts",
    load.data?.results || [],
    () => {
      setPage(1);
      load.reload();
    },
    "剧本会删除，已有任务的快照会保留。",
    `${page}:${q}`,
  );
  return (
    <>
      <Heading
        title="剧本与分镜"
        subtitle="一句台词，一个镜头，让故事有迹可循。"
      >
        <Link className="primary button" to="/scripts/new">
          ＋ 新建剧本
        </Link>
      </Heading>
      <div className="ai-bar">
        <div>
          <h3>从一个梗概，展开故事</h3>
          <p className="muted small">
            需配置自己的 LLM 服务，提交后可能产生供应商费用。
          </p>
        </div>
        <textarea
          aria-label="故事梗概"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="例如：在雨夜重逢的两位老朋友…"
          maxLength={4000}
        />
        <select
          aria-label="故事风格"
          value={style}
          onChange={(e) => setStyle(e.target.value)}
        >
          {["甜宠", "悬疑", "搞笑"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <button
          disabled={!topic || busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              const j = await api<{ id: number }>("jobs/", "POST", {
                kind: "llm",
                synopsis: topic,
                style,
                idempotency_key: key(),
              });
              nav("/jobs/" + j.id);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          AI 生成剧本
        </button>
      </div>
      <div className="toolbar">
        <input
          aria-label="搜索剧本"
          placeholder="搜索剧本标题…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
        />
      </div>
      <ErrorBox error={error || load.error} />
      {deletion.toolbar}
      {load.data?.results.length ? (
        <div className="script-grid">
          {load.data.results.map((s) => (
            <article className="script-card" key={s.id}>
              <label className="select-item">
                {deletion.checkbox(s.id)}选择
              </label>
              <div className="script-cover">
                <span>{s.style}</span>
                <strong>{s.title.slice(0, 12)}</strong>
                <i>STORY / {String(s.id).padStart(3, "0")}</i>
              </div>
              <div className="script-body">
                <Link to={"/scripts/" + s.id}>
                  <h3>{s.title}</h3>
                </Link>
                <p>{s.synopsis || "等待填入你的故事灵感…"}</p>
                <div className="card-meta">
                  <span>
                    {s.scenes.length} 个分镜 ·{" "}
                    {s.scenes.reduce((a, b) => a + b.duration, 0)} 秒
                  </span>
                  <Link to={"/scripts/" + s.id}>编辑 ↗</Link>
                  <button
                    className="text danger"
                    onClick={() => deletion.remove([s.id])}
                  >
                    删除
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <Empty text="第一段故事，等你写下">
          <Link to="/scripts/new">新建剧本 →</Link>
        </Empty>
      )}
      {load.data && (
        <Pager page={page} total={load.data.total} onChange={setPage} />
      )}
    </>
  );
}
