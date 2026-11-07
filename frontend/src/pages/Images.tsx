import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, key } from "../api";
import { useLoad } from "../hooks";
import { Heading, ErrorBox } from "../components";
type Provider = {
  id: number;
  name: string;
  model: string;
  service: string;
  active: boolean;
};
export default function Images() {
  const providers = useLoad(() => api<Provider[]>("providers/"));
  const [provider, setProvider] = useState(""),
    [prompt, setPrompt] = useState(""),
    [size, setSize] = useState("1024x1024"),
    [count, setCount] = useState(1),
    [paid, setPaid] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const choices =
    providers.data?.filter((p) => p.service === "image" && p.active) || [];
  const nav = useNavigate();
  return (
    <>
      <Heading
        title="文生图"
        subtitle="生成角色、场景与分镜画面，保存到素材库后用于多图生视频。"
      />
      <ErrorBox error={error || providers.error} />
      <section className="panel compose-panel">
        {!choices.length && (
          <p className="error">
            请先在<Link to="/settings">个人与 API 配置</Link>添加“图片生成
            API”服务。
          </p>
        )}
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              const job = await api<{ id: number }>("jobs/", "POST", {
                kind: "image_api",
                provider_id: Number(provider),
                prompt,
                size,
                count,
                confirm_paid: paid,
                idempotency_key: key(),
              });
              nav(`/jobs/${job.id}`);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            图片 API 服务
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
            画面提示词
            <textarea
              required
              rows={7}
              maxLength={4000}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="描述人物外观、服装、场景、构图和画面风格…"
            />
          </label>
          <div className="form-row">
            <label>
              图片尺寸
              <input
                required
                value={size}
                maxLength={20}
                onChange={(e) => setSize(e.target.value)}
                placeholder="例如 1024x1024"
              />
            </label>
            <label>
              生成张数
              <input
                type="number"
                min={1}
                max={4}
                required
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
              />
            </label>
          </div>
          <p className="muted small">
            每次最多4张。尺寸、张数及模型支持范围以供应商为准，接口映射需使用
            size 和 count 占位符。生成图片会优化为适合轻量视频制作的 JPEG 素材。
          </p>
          <label className="checkbox">
            <input
              type="checkbox"
              required
              checked={paid}
              onChange={(e) => setPaid(e.target.checked)}
            />
            我确认发送提示词给自己的供应商，并承担 API 调用费用。
          </label>
          <button
            className="primary"
            disabled={busy || !paid || !provider || !prompt.trim()}
          >
            {busy ? "提交中…" : "生成图片 →"}
          </button>
        </form>
      </section>
      <p>
        <Link to="/assets">查看图片素材 →</Link>　
        <Link to="/compose">制作多图视频 →</Link>
      </p>
    </>
  );
}
