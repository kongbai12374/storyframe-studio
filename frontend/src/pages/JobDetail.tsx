import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Job, key, statuses } from "../api";
import { usePoll } from "../hooks";
import { Heading, ErrorBox } from "../components";
export default function JobDetail() {
  const { id } = useParams(),
    [error, setError] = useState("");
  const load = usePoll(() => api<Job>(`jobs/${id}/`), [id]);
  const j = load.data;
  return (
    <>
      <Link to="/jobs">← 任务中心</Link>
      <Heading
        title={"任务 #" + id}
        subtitle="进度由后台任务更新，关闭页面不会中断合成。"
      />
      <ErrorBox error={error || load.error} />
      {j && (
        <>
          <div className="panel">
            <div className="section-title">
              <h2>{j.stage}</h2>
              <span className={"badge " + j.status}>{statuses[j.status]}</span>
            </div>
            <div className="progress-track large">
              <div style={{ width: j.progress + "%" }} />
            </div>
            <p className="muted">
              进度 {j.progress}% · 已执行 {j.attempts} 次
            </p>
            <ErrorBox error={j.error} />
            {j.remote_status?.task_id && (
              <p className="muted">
                供应商任务ID：{j.remote_status.task_id} · 状态：
                {j.remote_status.status || "待查询"}
              </p>
            )}
            {j.remote_status?.cancellation && (
              <p className="muted small">
                本地已取消。供应商取消结果：{j.remote_status.cancellation}
                ；费用请在供应商侧核查。
              </p>
            )}
            <div className="actions">
              {!["queued", "running", "cancel_requested"].includes(
                j.status,
              ) && (
                <button
                  className="danger"
                  onClick={async () => {
                    if (
                      !confirm(
                        "永久删除任务记录与视频文件？生成的图片和剧本会保留。",
                      )
                    )
                      return;
                    try {
                      await api(`jobs/${id}/`, "DELETE");
                      location.href = "/jobs";
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  删除任务
                </button>
              )}
              {j.remote_status &&
                Object.keys(j.remote_status).length > 0 &&
                ["failed", "interrupted", "cancelled"].includes(j.status) && (
                  <button
                    className="danger"
                    onClick={async () => {
                      if (
                        !confirm(
                          "重新生成将新建供应商任务，可能重复收费。请先核查原任务，确认仍要新生成？",
                        )
                      )
                        return;
                      try {
                        const n = await api<Job>(`jobs/${id}/retry/`, "POST", {
                          idempotency_key: key(),
                          confirm_paid: true,
                          new_generation: true,
                        });
                        location.href = "/jobs/" + n.id;
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }}
                  >
                    重新生成（可能再次计费）
                  </button>
                )}
              {["queued", "running", "cancel_requested"].includes(j.status) && (
                <button
                  className="danger"
                  onClick={async () => {
                    try {
                      await api(`jobs/${id}/cancel/`, "POST", {});
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  取消任务
                </button>
              )}
              {["failed", "interrupted", "cancelled"].includes(j.status) && (
                <button
                  onClick={async () => {
                    if (
                      j.may_charge &&
                      !confirm(
                        "请先核查供应商是否已扣费。重新执行可能再次产生费用，是否继续？",
                      )
                    )
                      return;
                    try {
                      const next = await api<Job>(`jobs/${id}/retry/`, "POST", {
                        idempotency_key: key(),
                        confirm_paid: true,
                      });
                      location.href = "/jobs/" + next.id;
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  查询原任务 / 核查后重试
                </button>
              )}
              {j.result.script_id != null && (
                <Link to={"/scripts/" + j.result.script_id}>
                  打开生成剧本 →
                </Link>
              )}
            </div>
          </div>
          {Array.isArray(j.result.asset_ids) && (
            <section className="panel">
              <h2>生成图片已保存到素材库</h2>
              <div className="asset-grid">
                {(j.result.asset_ids as number[]).map((assetId) => (
                  <a
                    key={assetId}
                    href={`/api/assets/${assetId}/file/`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <img
                      className="large-preview"
                      src={`/api/assets/${assetId}/file/`}
                      alt={`生成图片 #${assetId}`}
                    />
                  </a>
                ))}
              </div>
              <div className="actions">
                <Link to="/assets">打开素材库 →</Link>
                <Link to="/compose">选择多图制作视频 →</Link>
              </div>
            </section>
          )}
          {j.download_url && (
            <div className="panel">
              <h2>作品已就绪</h2>
              <video
                className="result-video"
                controls
                preload="metadata"
                src={j.download_url}
              />
              <a
                className="primary button"
                href={j.download_url + "?download=1"}
              >
                下载视频 ↓
              </a>
            </div>
          )}
          <div className="panel">
            <h2>运行日志</h2>
            {j.logs?.map((l, i) => (
              <div className="log-row" key={i}>
                <span>{l.message}</span>
                <time>{new Date(l.created_at).toLocaleString()}</time>
              </div>
            ))}
          </div>
          {j.kind === "canvas" && j.result.nodes != null && (
            <div className="panel">
              <h2>节点结果</h2>
              <pre>{JSON.stringify(j.result.nodes, null, 2)}</pre>
            </div>
          )}
        </>
      )}
    </>
  );
}
