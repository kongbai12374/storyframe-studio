import { useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { api, Page, Script, key } from "../api";
import { useLoad } from "../hooks";
import { Heading, ErrorBox } from "../components";
export default function Compose() {
  const [params] = useSearchParams(),
    [id, setId] = useState(params.get("script") || ""),
    [tts, setTTS] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const nav = useNavigate(),
    load = useLoad(() => api<Page<Script>>("scripts/?limit=100"));
  const selected = load.data?.results.find((s) => s.id === Number(id));
  return (
    <>
      <Heading
        title="让故事成为作品"
        subtitle="确认分镜与素材，交给工作室有序合成。"
      />
      <div className="compose-steps">
        <span className="active">01 选择剧本</span>
        <span>02 确认素材</span>
        <span>03 提交合成</span>
      </div>
      <ErrorBox error={error || load.error} />
      <div className="panel compose-panel">
        <h2>选择这次要讲的故事</h2>
        <label>
          剧本
          <select value={id} onChange={(e) => setId(e.target.value)}>
            <option value="">请选择剧本</option>
            {load.data?.results.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
        </label>
        {selected && (
          <>
            <div className="summary-box">
              <h3>{selected.title}</h3>
              <p>
                {selected.scenes.length} 个分镜 ·{" "}
                {selected.scenes.reduce((a, s) => a + s.duration, 0)} 秒 · 版本{" "}
                {selected.revision}
              </p>
              <p>
                {selected.scenes.filter((s) => s.image_id).length}/
                {selected.scenes.length} 个分镜已关联图片
              </p>
              <Link to={"/scripts/" + selected.id}>编辑分镜与素材 →</Link>
            </div>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={tts}
                onChange={(e) => setTTS(e.target.checked)}
              />
              无上传音频的分镜使用我的 TTS 服务（可能产生费用）
            </label>
            <p className="muted">
              不勾选时，没有上传音频的分镜会生成无配音视频，字幕仍正常显示。
            </p>
            <div className="specs">
              <span>1280 × 720</span>
              <span>24 FPS</span>
              <span>H.264 / AAC</span>
              <span>最长 60 秒</span>
            </div>
            <button
              className="primary"
              disabled={busy || selected.scenes.some((s) => !s.image_id)}
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  const j = await api<{ id: number }>("jobs/", "POST", {
                    kind: "compose",
                    script_id: Number(id),
                    use_tts: tts,
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
              {busy ? "正在提交…" : "确认素材并开始合成 →"}
            </button>
          </>
        )}
      </div>
    </>
  );
}
