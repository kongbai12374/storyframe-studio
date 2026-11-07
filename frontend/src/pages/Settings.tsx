import { useState } from "react";
import { api, User } from "../api";
import { useLoad } from "../hooks";
import { Heading, ErrorBox } from "../components";
type Provider = {
  id: number;
  name: string;
  service: string;
  base_url: string;
  model: string;
  key_hint: string;
  active: boolean;
  video_config?: Record<string, unknown>;
};
const defaultVideoConfig = {
  mode: "async",
  submit_path: "/videos",
  poll_path: "/videos/{{task_id}}",
  cancel_path: "",
  cancel_method: "POST",
  content_path: "",
  auth_header: "Authorization",
  auth_prefix: "Bearer ",
  request_body: {
    model: "{{model}}",
    prompt: "{{prompt}}",
    duration: "{{seconds}}",
    size: "{{size}}",
  },
  task_id_field: "id",
  status_field: "status",
  progress_field: "progress",
  video_url_field: "video_url",
  success_values: ["completed", "succeeded", "success"],
  failure_values: ["failed", "error", "cancelled", "canceled"],
  poll_seconds: 5,
};
const defaultImageConfig = {
  ...defaultVideoConfig,
  mode: "sync",
  submit_path: "/images/generations",
  poll_path: "",
  request_body: {
    model: "{{model}}",
    prompt: "{{prompt}}",
    size: "{{size}}",
    n: "{{count}}",
  },
  video_url_field: "data",
  output_format: "base64",
};
const defaultTtsConfig = {
  ...defaultVideoConfig,
  submit_path: "/api/v1/comfyui/comfyui_workflow/indextts2-v1",
  poll_path: "/api/v1/comfyui/comfyui_workflow/result/{{task_id}}",
  auth_prefix: "",
  request_body: {
    prompt_text: "{{text}}",
    prompt_simple: "{{audio_url}}",
    emo_control_method: "与音色参考音频相同",
  },
  task_id_field: "data.task_id",
  status_field: "data.status",
  progress_field: "",
  video_url_field: "data.results.0.url",
  success_values: ["SUCCESS", "completed"],
};
export default function Settings() {
  const [ttsWorkflow, setTtsWorkflow] = useState(false);
  const [videoConfig, setVideoConfig] = useState(
    JSON.stringify(defaultVideoConfig, null, 2),
  );
  const user = useLoad(() => api<User>("auth/me/")),
    providers = useLoad(() => api<Provider[]>("providers/"));
  const [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [editing, setEditing] = useState<number | null>(null),
    [form, setForm] = useState({
      name: "",
      service: "llm",
      base_url: "https://api.openai.com/v1",
      model: "",
      api_key: "",
      active: true,
    }),
    [name, setName] = useState(""),
    [oldPassword, setOldPassword] = useState(""),
    [password, setPassword] = useState("");
  async function profile(body: unknown) {
    try {
      await api("auth/me/", "PATCH", body);
      setMessage("已更新");
      user.reload();
      setPassword("");
      setOldPassword("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <Heading
        title="个人与 API 配置"
        subtitle="连接自己的服务，让工作室按你的方式创作。"
      />
      <ErrorBox error={error || providers.error || user.error} />
      {message && (
        <p className="success" role="status">
          {message}
        </p>
      )}
      <div className="settings-grid">
        <section className="panel">
          <h2>个人资料</h2>
          <p className="muted">账号：{user.data?.username}</p>
          <label>
            显示名称
            <input
              value={name}
              placeholder={user.data?.name || user.data?.username}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button onClick={() => profile({ name })}>保存名称</button>
          <hr />
          <label>
            原密码
            <input
              type="password"
              autoComplete="current-password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
            />
          </label>
          <label>
            新密码
            <input
              type="password"
              autoComplete="new-password"
              minLength={10}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button
            disabled={password.length < 10 || !oldPassword}
            onClick={() => profile({ old_password: oldPassword, password })}
          >
            修改密码
          </button>
          <hr />
          <p>
            存储：{((user.data?.used_bytes || 0) / 1024 ** 2).toFixed(1)} /{" "}
            {((user.data?.quota_bytes || 0) / 1024 ** 2).toFixed(0)} MB
          </p>
          <p>API 调用次数余额：{user.data?.api_calls_remaining}</p>
        </section>
        <section className="panel">
          <h2>{editing ? "编辑服务" : "添加 AI 服务"}</h2>
          <p className="muted small">
            支持 OpenAI 风格的 chat/completions 与 audio/speech
            协议。模型由你填写，需供应商实际支持。费用记入你的供应商账户。
          </p>
          <p className="muted small">
            图片和视频支持用户自选供应商的JSON同步/异步接口；请按供应商文档填写映射，特殊签名、multipart上传等协议需专用适配器。检查配置不会发送付费请求。
          </p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              try {
                await api(
                  editing ? `providers/${editing}/` : "providers/",
                  editing ? "PUT" : "POST",
                  {
                    ...form,
                    ...(["video", "image"].includes(form.service) ||
                    (form.service === "tts" && ttsWorkflow)
                      ? { video_config: JSON.parse(videoConfig) }
                      : form.service === "tts"
                        ? { video_config: {} }
                        : {}),
                  },
                );
                setForm({ ...form, api_key: "" });
                setEditing(null);
                setMessage("服务配置已加密保存");
                providers.reload();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              名称
              <input
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>
            <div className="form-row">
              <label>
                服务类型
                <select
                  value={form.service}
                  onChange={(e) => {
                    setTtsWorkflow(false);
                    setVideoConfig(
                      JSON.stringify(
                        e.target.value === "image"
                          ? defaultImageConfig
                          : defaultVideoConfig,
                        null,
                        2,
                      ),
                    );
                    setForm({
                      ...form,
                      service: e.target.value,
                      ...(["video", "image"].includes(e.target.value)
                        ? { base_url: "", model: "" }
                        : {}),
                    });
                  }}
                >
                  <option value="llm">LLM 剧本生成</option>
                  <option value="tts">TTS 配音</option>
                  <option value="video">视频生成 API</option>
                  <option value="image">图片生成 API</option>
                </select>
              </label>
              <label>
                模型名称
                <input
                  required
                  value={form.model}
                  onChange={(e) => setForm({ ...form, model: e.target.value })}
                  placeholder="供应商支持的模型ID"
                />
              </label>
            </div>
            <label>
              API Base URL
              <input
                type="url"
                required
                value={form.base_url}
                onChange={(e) => setForm({ ...form, base_url: e.target.value })}
              />
            </label>
            <label>
              API Key
              <input
                type="password"
                autoComplete="off"
                required={!editing}
                value={form.api_key}
                placeholder={editing ? "留空保留原密钥" : "密钥将加密存储"}
                onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              />
            </label>
            {form.service === "tts" && (
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={ttsWorkflow}
                  onChange={(e) => {
                    setTtsWorkflow(e.target.checked);
                    if (e.target.checked)
                      setVideoConfig(JSON.stringify(defaultTtsConfig, null, 2));
                  }}
                />
                使用 JSON 工作流配音（如 AutoDL IndexTTS2）
              </label>
            )}
            {(["video", "image"].includes(form.service) ||
              (form.service === "tts" && ttsWorkflow)) && (
              <label>
                {form.service === "image"
                  ? "图片"
                  : form.service === "tts"
                    ? "配音"
                    : "视频"}
                接口映射（JSON）
                <textarea
                  aria-label="生成接口映射"
                  rows={20}
                  value={videoConfig}
                  onChange={(e) => setVideoConfig(e.target.value)}
                />
                {form.service === "image" && (
                  <div className="actions">
                    <button
                      type="button"
                      onClick={() =>
                        setVideoConfig(
                          JSON.stringify(defaultImageConfig, null, 2),
                        )
                      }
                    >
                      载入图片 Base64 示例
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setVideoConfig(
                          JSON.stringify(
                            {
                              ...defaultImageConfig,
                              output_format: "url",
                              request_body: {
                                ...defaultImageConfig.request_body,
                                response_format: "url",
                              },
                            },
                            null,
                            2,
                          ),
                        )
                      }
                    >
                      载入图片 URL 示例
                    </button>
                  </div>
                )}
                <span className="muted small">
                  请修改提交/查询路径、状态与成片URL字段。data.0.url
                  表示数组首项。密钥只填上方专用字段。支持{" "}
                  {
                    "{{model}}、{{prompt}}、{{seconds}}、{{size}}、{{image_base64}}、{{image_data_url}}、{{images_base64}}、{{images_data_urls}}、{{count}}、{{text}}、{{audio_url}}、{{image_url_0}}、{{image_url_1}}"
                  }
                  。工作流配音使用 text 文本和 audio_url
                  参考音频链接；参考音频在画布TTS节点选择。同步接口设置mode为sync。多图数组须独占整个字符串占位符。图片结果字段仍使用video_url_field：可指向图片URL、Base64字符串或结果数组，output_format选择url或base64。
                </span>
              </label>
            )}
            <label className="checkbox">
              <input
                type="checkbox"
                checked={form.active}
                onChange={(e) => setForm({ ...form, active: e.target.checked })}
              />
              启用此服务
            </label>
            <button className="primary" disabled={busy}>
              {busy ? "保存中…" : "加密保存"}
            </button>
            {editing && (
              <button type="button" onClick={() => setEditing(null)}>
                取消编辑
              </button>
            )}
          </form>
        </section>
      </div>
      <section className="panel">
        <h2>已配置服务</h2>
        {providers.data?.length ? (
          providers.data.map((p) => (
            <div className="provider-row" key={p.id}>
              <div>
                <strong>{p.name}</strong>
                <p className="muted small">
                  {p.service.toUpperCase()} · {p.model} · {p.key_hint} ·{" "}
                  {p.active ? "已启用" : "已停用"}
                </p>
              </div>
              <div className="actions">
                <button
                  onClick={() => {
                    setEditing(p.id);
                    setTtsWorkflow(
                      p.service === "tts" &&
                        Boolean(
                          p.video_config && Object.keys(p.video_config).length,
                        ),
                    );
                    setVideoConfig(
                      JSON.stringify(
                        p.video_config && Object.keys(p.video_config).length
                          ? p.video_config
                          : p.service === "image"
                            ? defaultImageConfig
                            : defaultVideoConfig,
                        null,
                        2,
                      ),
                    );
                    setForm({
                      name: p.name,
                      service: p.service,
                      base_url: p.base_url,
                      model: p.model,
                      api_key: "",
                      active: p.active,
                    });
                  }}
                >
                  编辑
                </button>
                <button
                  onClick={async () => {
                    try {
                      const r = await api<{ detail: string }>(
                        `providers/${p.id}/test/`,
                        "POST",
                        {},
                      );
                      setMessage(r.detail);
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  检查配置
                </button>
                <button
                  className="danger"
                  onClick={async () => {
                    if (confirm("删除这个服务配置？"))
                      try {
                        await api(`providers/${p.id}/`, "DELETE");
                        providers.reload();
                      } catch (e) {
                        setError((e as Error).message);
                      }
                  }}
                >
                  删除
                </button>
              </div>
            </div>
          ))
        ) : (
          <p className="muted">尚未配置，手动编辑和上传素材合成仍可使用。</p>
        )}
      </section>
    </>
  );
}
