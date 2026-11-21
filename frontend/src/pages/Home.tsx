import { Link } from "react-router-dom";
import { api } from "../api";
import { useLoad } from "../hooks";
import { ErrorBox } from "../components";
type Dashboard = {
  scripts: number;
  assets: number;
  canvases: number;
  jobs: Record<string, number>;
  profile: {
    used_bytes: number;
    quota_bytes: number;
    api_calls_remaining: number;
  };
};
function formatBytes(bytes: number) {
  return bytes < 1024 * 1024
    ? `${Math.ceil(bytes / 1024)} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
export default function Home({ displayName }: { displayName: string }) {
  const { data, error } = useLoad(() => api<Dashboard>("dashboard/"));
  const storagePercent = data?.profile.quota_bytes
    ? Math.min(
        100,
        Math.round(
          (data.profile.used_bytes / data.profile.quota_bytes) * 100,
        ),
      )
    : 0;
  const stats = [
    { label: "剧本与分镜", count: data?.scripts, path: "/scripts" },
    { label: "创作画布", count: data?.canvases, path: "/canvases" },
    { label: "素材文件", count: data?.assets, path: "/assets" },
    {
      label: "已完成任务",
      count: data?.jobs.succeeded || 0,
      path: "/jobs",
    },
  ];
  return (
    <>
      <div className="welcome">
        <div>
          <p className="eyebrow">创作工作台</p>
          <h1>
            欢迎回来，{displayName}
            <br />
            今天继续你的创作。
          </h1>
          <p>查看项目进度，或从常用操作继续创作。</p>
          <Link className="primary button" to="/canvases">
            打开创作画布
          </Link>
          <Link className="button subtle" to="/scripts">
            管理剧本
          </Link>
        </div>
        <div className="welcome-art">
          <div className="dashboard-summary">
            <span className="status-dot" />
            <strong>
              {(data?.jobs.queued || 0) +
                (data?.jobs.running || 0) +
                (data?.jobs.cancel_requested || 0)} 项任务处理中
            </strong>
            <Link to="/jobs">查看任务 →</Link>
          </div>
        </div>
      </div>
      <ErrorBox error={error} />
      <div className="stat-grid">
        {stats.map(({ label, count, path }) => (
          <Link className="stat-card" key={label} to={path}>
            <span>{label}</span>
            <strong>{count ?? "—"}</strong>
            <small>查看与管理 →</small>
          </Link>
        ))}
      </div>
      <div className="section-title">
        <h2>常用操作</h2>
        <span className="muted">按创作进度选择下一步</span>
      </div>
      <div className="steps-grid">
        {[
          ["01", "编写剧本", "补充故事梗概、台词和分镜。", "/scripts"],
          ["02", "整理素材", "上传并管理图片、配音素材。", "/assets"],
          ["03", "编排流程", "在画布中连接节点并运行。", "/canvases"],
          ["04", "查看任务", "跟踪生成进度并查看成片。", "/jobs"],
        ].map(([n, t, d, to]) => (
          <Link className="step-card" to={to} key={n}>
            <span>{n}</span>
            <h3>{t}</h3>
            <p>{d}</p>
          </Link>
        ))}
      </div>
      <div className="info-strip">
        <strong>资源用量</strong>
        <span>
          素材存储 {data ? formatBytes(data.profile.used_bytes) : "加载中"}
          {data && ` / ${formatBytes(data.profile.quota_bytes)}`}
        </span>
        <div
          className="storage-track"
          role="progressbar"
          aria-label="素材存储用量"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={storagePercent}
        >
          <span style={{ width: `${storagePercent}%` }} />
        </div>
        <span>可用 AI 调用 {data?.profile.api_calls_remaining ?? "—"} 次</span>
        <Link to="/settings">账号与服务配置 →</Link>
      </div>
    </>
  );
}
