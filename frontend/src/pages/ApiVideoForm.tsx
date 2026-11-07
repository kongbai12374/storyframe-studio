import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, Asset, Page, Script, key } from "../api";
import { useLoad } from "../hooks";
import { Heading, ErrorBox } from "../components";
import LocalCompose from "./LocalCompose";
type Provider = {
  id: number;
  name: string;
  model: string;
  service: string;
  active: boolean;
};
export default function ApiVideoForm() {
  const [mode, setMode] = useState("api"),
    [prompt, setPrompt] = useState(""),
    [provider, setProvider] = useState(""),
    [images, setImages] = useState<number[]>([]),
    [seconds, setSeconds] = useState(5),
    [size, setSize] = useState("1280x720"),
    [paid, setPaid] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const nav = useNavigate(),
    [params] = useSearchParams();
  const providers = useLoad(() => api<Provider[]>("providers/"));
  const scripts = useLoad(() => api<Page<Script>>("scripts/?limit=100"));
  const assets = useLoad(() =>
    api<Page<Asset>>("assets/?kind=image&limit=100"),
  );
  const choices =
    providers.data?.filter((p) => p.service === "video" && p.active) || [];
  function useScript(id: string) {
    const s = scripts.data?.results.find((s) => s.id === Number(id));
    if (s)
      setPrompt(
        (
          s.title +
          "\n" +
          s.synopsis +
          "\n" +
          s.scenes.map((x) => x.description + " " + x.dialogue).join("\n")
        ).slice(0, 4000),
      );
  }
  useEffect(() => {
    if (scripts.data && params.get("script")) useScript(params.get("script")!);
  }, [scripts.data]);
  return (
    <>
      <div className="toolbar">
        <button
          className={mode === "api" ? "primary" : ""}
          onClick={() => setMode("api")}
        >
          用户 API 视频生成
        </button>
        <button
          className={mode === "local" ? "primary" : ""}
          onClick={() => setMode("local")}
        >
          本地图片与字幕合成
        </button>
      </div>
      {mode === "local" ? (
        <LocalCompose />
      ) : (
        <>
          <Heading
            title="使用自己的 API 生成视频"
            subtitle="选择供应商、编写提示词，由你的 API 生成视频，工作室负责查询进度与保存结果。"
          />
          <ErrorBox
            error={error || providers.error || scripts.error || assets.error}
          />
          <div className="panel compose-panel">
            <h2>视频生成参数</h2>
            {!choices.length && (
              <p className="error">
                尚未配置视频生成API。
                <Link to="/settings">前往个人与API配置添加 →</Link>
              </p>
            )}
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                setError("");
                try {
                  const j = await api<{ id: number }>("jobs/", "POST", {
                    kind: "video_api",
                    provider_id: Number(provider),
                    prompt,
                    seconds,
                    size,
                    image_ids: images,
                    confirm_paid: paid,
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
              <label>
                视频 API 服务
                <select
                  required
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                >
                  <option value="">请选择自己的供应商配置</option>
                  {choices.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} · {p.model}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                从剧本提取提示词（可选）
                <select
                  defaultValue=""
                  onChange={(e) => useScript(e.target.value)}
                >
                  <option value="">手动输入提示词</option>
                  {scripts.data?.results.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                视频提示词
                <textarea
                  required
                  maxLength={4000}
                  rows={7}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="描述人物、场景、动作、镜头运动和画面风格…"
                />
              </label>
              <div className="form-row">
                <label>
                  生成时长（秒）
                  <input
                    type="number"
                    min={1}
                    max={60}
                    required
                    value={seconds}
                    onChange={(e) => setSeconds(Number(e.target.value))}
                  />
                </label>
                <label>
                  画面方向
                  <select
                    value={size}
                    onChange={(e) => setSize(e.target.value)}
                  >
                    <option value="1280x720">横屏 1280×720</option>
                    <option value="720x1280">竖屏 720×1280</option>
                  </select>
                </label>
              </div>
              <fieldset className="reference-picker">
                <legend>参考图片（可选，最多9张）</legend>
                <p className="muted small">
                  按勾选顺序发送。单图模板使用第一张，多图模板需使用
                  images_base64 或 images_data_urls
                  数组。供应商必须实际支持多图输入。
                </p>
                <div className="reference-grid">
                  {assets.data?.results.map((a) => (
                    <label
                      key={a.id}
                      className={
                        images.includes(a.id)
                          ? "reference-card chosen"
                          : "reference-card"
                      }
                    >
                      <img src={a.thumbnail_url} alt="" loading="lazy" />
                      <span>
                        <input
                          type="checkbox"
                          checked={images.includes(a.id)}
                          disabled={
                            !images.includes(a.id) && images.length >= 9
                          }
                          onChange={(e) =>
                            setImages(
                              e.target.checked
                                ? [...images, a.id]
                                : images.filter((id) => id !== a.id),
                            )
                          }
                        />
                        {a.name}
                      </span>
                    </label>
                  ))}
                </div>
                <ol className="reference-order">
                  {images.map((id, i) => (
                    <li key={id}>
                      {assets.data?.results.find((a) => a.id === id)?.name}
                      <button
                        type="button"
                        aria-label={`参考图${i + 1}前移`}
                        disabled={i === 0}
                        onClick={() => {
                          const next = [...images];
                          [next[i - 1], next[i]] = [next[i], next[i - 1]];
                          setImages(next);
                        }}
                      >
                        前移
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          setImages(images.filter((x) => x !== id))
                        }
                      >
                        移除
                      </button>
                    </li>
                  ))}
                </ol>
                <Link to="/images">先生成参考图片 →</Link>
              </fieldset>
              <label className="checkbox">
                <input
                  type="checkbox"
                  required
                  checked={paid}
                  onChange={(e) => setPaid(e.target.checked)}
                />
                我确认将提示词及所选参考图发送给自己的供应商，并承担其API调用费用。
              </label>
              <p className="muted small">
                系统不会自动重复提交付费生成请求。取消本地等待不保证供应商停止生成或退费；超时后可查询原任务。
              </p>
              <button
                className="primary"
                disabled={busy || !paid || !provider || !prompt.trim()}
              >
                {busy ? "提交中…" : "提交至我的视频 API →"}
              </button>
            </form>
          </div>
        </>
      )}
    </>
  );
}
