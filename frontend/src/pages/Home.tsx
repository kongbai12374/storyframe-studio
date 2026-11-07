import { Link } from "react-router-dom";
import { api } from "../api";
import { useLoad } from "../hooks";
import { ErrorBox } from "../components";
type Dashboard = {
  scripts: number;
  assets: number;
  canvases: number;
  jobs: Record<string, number>;
  profile: { used_bytes: number; quota_bytes: number };
};
export default function Home() {
  const { data, error } = useLoad(() => api<Dashboard>("dashboard/"));
  return (
    <>
      <div className="welcome">
        <div>
          <p className="eyebrow">CREATE SOMETHING WORTH WATCHING</p>
          <h1>
            每个好故事，
            <br />
            都从一个想法开始。
          </h1>
          <p>写下剧本，连接画面，让想象在镜头里生长。</p>
          <Link className="primary button" to="/canvases">
            打开创作画布 ↗
          </Link>
          <Link className="button subtle" to="/scripts/new">
            新建剧本
          </Link>
        </div>
        <div className="welcome-art">
          <span className="art-number">01</span>
          <div className="art-window">
            <span>STORY IN MOTION</span>
            <strong>
              一镜，
              <br />
              一个新世界。
            </strong>
            <i>◁ ▷ ━━━━━━━ ●</i>
          </div>
        </div>
      </div>
      <ErrorBox error={error} />
      <div className="stat-grid">
        {[
          ["剧本草稿", data?.scripts, "▤"],
          ["创作画布", data?.canvases, "⌘"],
          ["素材收藏", data?.assets, "▧"],
          ["已完成视频", data?.jobs.succeeded || 0, "▶"],
        ].map(([label, num, icon]) => (
          <article className="stat-card" key={label}>
            <span>
              {label}
              <i>{icon}</i>
            </span>
            <strong>{num ?? "—"}</strong>
            <small>属于你的创作积累</small>
          </article>
        ))}
      </div>
      <div className="section-title">
        <h2>从想法到成片</h2>
        <span className="muted">一步一步，保持专注</span>
      </div>
      <div className="steps-grid">
        {[
          ["01", "构思故事", "填写梗概、编写台词与分镜。", "/scripts"],
          ["02", "准备素材", "上传图片和配音，为故事找到画面。", "/assets"],
          ["03", "连接灵感", "在画布中整理节点与创作流程。", "/canvases"],
          ["04", "生成作品", "按顺序合成字幕、画面与声音。", "/compose"],
        ].map(([n, t, d, to]) => (
          <Link className="step-card" to={to} key={n}>
            <span>{n}</span>
            <h3>{t} ↗</h3>
            <p>{d}</p>
          </Link>
        ))}
      </div>
      <div className="info-strip">
        <strong>轻量工作室</strong>
        <span>720p · 最长60秒 · 单任务合成</span>
        <Link to="/settings">配置自己的 AI 服务 →</Link>
      </div>
    </>
  );
}
