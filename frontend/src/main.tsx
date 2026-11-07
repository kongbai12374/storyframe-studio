import React, { Suspense, lazy, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Routes,
  Route,
  NavLink,
  Navigate,
  Link,
  useLocation,
} from "react-router-dom";
import { api, User } from "./api";
import "./style.css";
const Home = lazy(() => import("./pages/Home"));
const Scripts = lazy(() => import("./pages/Scripts"));
const Editor = lazy(() => import("./pages/Editor"));
const Images = lazy(() => import("./pages/Images"));
const Assets = lazy(() => import("./pages/Assets"));
const Jobs = lazy(() => import("./pages/Jobs"));
const JobDetail = lazy(() => import("./pages/JobDetail"));
const Settings = lazy(() => import("./pages/Settings"));
const Canvas = lazy(() => import("./pages/Creator/Canvas"));
const Canvases = lazy(() => import("./pages/Canvases"));
const Compose = lazy(() => import("./pages/Compose"));
function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [name, setName] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="login-screen">
      <div className="login-intro">
        <div className="brand">
          ◈ 镜序 <small>STORYFRAME</small>
        </div>
        <p className="eyebrow">A SMALL STUDIO FOR BIG STORIES</p>
        <h1>
          把一个念头，
          <br />
          拍成一段故事。
        </h1>
        <p>
          从第一句台词到最后一个镜头，
          <br />
          在属于你的工作室里，慢慢成形。
        </p>
        <div className="frame-art">
          <span>SCENE 01</span>
          <div>
            光影之间
            <br />
            <em>故事正在发生</em>
          </div>
          <i>01:00 / 720P</i>
        </div>
      </div>
      <form
        className="login-card"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            onLogin(
              await api<User>("auth/login/", "POST", {
                username: name,
                password,
              }),
            );
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <p className="eyebrow">WELCOME TO YOUR STUDIO</p>
        <h2>进入创作工作室</h2>
        <p className="muted">使用管理员为你创建的账号登录。</p>
        <label>
          账号
          <input
            autoComplete="username"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          密码
          <input
            autoComplete="current-password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <p className="error" role="alert">
          {error}
        </p>
        <button className="primary full" disabled={busy}>
          {busy ? "登录中…" : "开始创作 →"}
        </button>
        <p className="muted small">工作室采用邀请制，暂不开放公开注册。</p>
      </form>
    </div>
  );
}
function App() {
  const [user, setUser] = useState<User | null>(null),
    [ready, setReady] = useState(false);
  const location = useLocation();
  useEffect(() => {
    api<User>("auth/me/")
      .then(setUser)
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);
  if (!ready) return <div className="loading">正在打开工作室…</div>;
  if (!user) return <Login onLogin={setUser} />;
  return (
    <div className="shell">
      <aside>
        <Link to="/" className="brand">
          ◈ 镜序<small>STORYFRAME STUDIO</small>
        </Link>
        <div className="workspace">
          <span className="workspace-icon">镜</span>
          <div>
            个人创作空间<small>轻量 · 专注 · 有序</small>
          </div>
        </div>
        <p className="nav-label">创作工作室</p>
        <nav>
          {[
            ["/", "◫", "工作台"],
            ["/canvases", "⌘", "创作画布"],
            ["/scripts", "▤", "剧本与分镜"],
            ["/assets", "▧", "素材库"],
            ["/images", "✧", "文生图"],
            ["/compose", "▶", "视频生成"],
            ["/jobs", "◷", "任务中心"],
            ["/settings", "⚙", "个人与 API 配置"],
          ].map(([to, icon, title]) => (
            <NavLink key={to} to={to} end={to === "/"}>
              <span>{icon}</span>
              {title}
            </NavLink>
          ))}
        </nav>
        <div className="aside-foot">
          <div className="avatar">
            {user.username.slice(0, 1).toUpperCase()}
          </div>
          <div>
            {user.name || user.username}
            <small>{user.is_admin ? "工作室管理员" : "创作者"}</small>
          </div>
          <button
            className="icon"
            title="退出登录"
            onClick={async () => {
              await api("auth/logout/", "POST", {});
              setUser(null);
            }}
          >
            ↗
          </button>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>
            工作室 <i>/</i>{" "}
            {location.pathname.startsWith("/creator") ? "创作画布" : "创作空间"}
          </span>
          <div className="top-right">
            <span className="status-dot" /> 单任务有序运行{" "}
            {user.is_admin && (
              <a href="/admin/" target="_blank">
                管理后台 ↗
              </a>
            )}
          </div>
        </header>
        <div className="content">
          <Suspense fallback={<div className="loading">正在加载…</div>}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Navigate to="/" />} />
              <Route path="/scripts" element={<Scripts />} />
              <Route path="/scripts/:id" element={<Editor />} />
              <Route path="/assets" element={<Assets />} />
              <Route path="/images" element={<Images />} />
              <Route path="/jobs" element={<Jobs />} />
              <Route path="/jobs/:id" element={<JobDetail />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/compose" element={<Compose />} />
              <Route path="/canvases" element={<Canvases />} />
              <Route path="/creator/canvas/:id" element={<Canvas />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </Suspense>
        </div>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>,
);
