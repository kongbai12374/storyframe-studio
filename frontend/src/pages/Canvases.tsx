import { useDeletion } from "../deletion";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Page } from "../api";
import { useLoad } from "../hooks";
import { Heading, Empty, ErrorBox, Pager } from "../components";
export default function Canvases() {
  const [page, setPage] = useState(1),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    nav = useNavigate();
  const load = useLoad(
    () =>
      api<
        Page<{ id: number; name: string; revision: number; updated_at: string }>
      >(`canvases/?page=${page}`),
    [page],
  );
  const deletion = useDeletion(
    "canvases",
    load.data?.results || [],
    () => {
      setPage(1);
      load.reload();
    },
    "只删除画布，素材与任务会保留。",
    page,
  );
  return (
    <>
      <Heading
        title="创作画布"
        subtitle="把故事、画面与声音连接起来。在一张画布上，看见创作的全貌。"
      >
        <button
          className="primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              const c = await api<{ id: number }>("canvases/", "POST", {
                name: "未命名创作画布",
              });
              nav("/creator/canvas/" + c.id);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          ＋ 新建画布
        </button>
      </Heading>
      <ErrorBox error={error || load.error} />
      {deletion.toolbar}
      {load.data?.results.length ? (
        <div className="script-grid">
          {load.data.results.map((c) => (
            <article className="canvas-card" key={c.id}>
              <label className="select-item">
                {deletion.checkbox(c.id)}选择
              </label>
              <Link to={"/creator/canvas/" + c.id}>
                <div className="canvas-cover">
                  <i />
                  <i />
                  <i />
                  <span>⌘</span>
                </div>
                <h3>{c.name}</h3>
              </Link>
              <div className="card-meta">
                <span>
                  版本 {c.revision} ·{" "}
                  {new Date(c.updated_at).toLocaleDateString()}
                </span>
                <button
                  className="text danger"
                  onClick={async () => {
                    if (confirm("删除画布？素材和已有任务会保留。"))
                      try {
                        await api(`canvases/${c.id}/`, "DELETE");
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
        <Empty text="让灵感在画布上相连" />
      )}
      {load.data && (
        <Pager page={page} total={load.data.total} onChange={setPage} />
      )}
    </>
  );
}
