import { useDeletion } from "../deletion";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, Page, Job, statuses } from "../api";
import { usePoll } from "../hooks";
import { Heading, ErrorBox, Empty, Pager } from "../components";
export default function Jobs() {
  const [page, setPage] = useState(1),
    [tick, setTick] = useState(0);
  const { data, error } = usePoll(
    () => api<Page<Job>>(`jobs/?page=${page}`),
    [page, tick],
  );
  const deletion = useDeletion(
    "jobs",
    data?.results.filter(
      (j) => !["queued", "running", "cancel_requested"].includes(j.status),
    ) || [],
    () => {
      setPage(1);
      setTick((x) => x + 1);
    },
    "任务记录与视频文件会删除，已生成的图片和剧本会保留。",
    page,
  );
  return (
    <>
      <Heading
        title="任务中心"
        subtitle="每一步进展，都清晰可见。任务按顺序执行，离开页面也会继续。"
      />
      <ErrorBox error={error} />
      {deletion.toolbar}
      {data?.results.length ? (
        <div className="job-list">
          {data.results.map((j) => (
            <div className="job-row" key={j.id}>
              {!["queued", "running", "cancel_requested"].includes(j.status) &&
                deletion.checkbox(j.id)}
              <Link
                className="job-open"
                to={"/jobs/" + j.id}
                aria-label={`查看任务 #${j.id}`}
              >
                <div className="job-icon">
                  {j.kind === "canvas" ? "⌘" : j.kind === "llm" ? "▤" : "▶"}
                </div>
                <div className="job-description">
                  <strong>
                    #{j.id} ·{" "}
                    {j.kind === "image_api"
                      ? "AI 图片生成"
                      : j.kind === "canvas"
                        ? "画布流程"
                        : j.kind === "video_api"
                          ? "API 视频生成"
                          : j.kind === "llm"
                            ? "AI 剧本"
                            : "视频合成"}
                  </strong>
                  <p>{j.stage}</p>
                  <div className="progress-track">
                    <div style={{ width: j.progress + "%" }} />
                  </div>
                </div>
                <span className={"badge " + j.status}>
                  {statuses[j.status]}
                </span>
                <span className="muted small">{j.progress}%</span>
                <span className="job-view">查看 →</span>
              </Link>
              {!["queued", "running", "cancel_requested"].includes(
                j.status,
              ) && (
                <button
                  className="text danger"
                  onClick={() => deletion.remove([j.id])}
                >
                  删除
                </button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <Empty text="创作任务会在这里相遇">
          <Link to="/compose">开始一次合成 →</Link>
        </Empty>
      )}
      {data && <Pager page={page} total={data.total} onChange={setPage} />}
    </>
  );
}
