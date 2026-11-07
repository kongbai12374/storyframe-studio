import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, Asset, Page, Script, scene } from "../api";
import { Heading, ErrorBox } from "../components";
export default function Editor() {
  const { id } = useParams(),
    fresh = id === "new",
    nav = useNavigate();
  const [form, setForm] = useState<Script>({
      id: 0,
      title: "",
      synopsis: "",
      style: "甜宠",
      scenes: [scene()],
      revision: 1,
    }),
    [assets, setAssets] = useState<Asset[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [dirty, setDirty] = useState(false);
  useEffect(() => {
    api<Page<Asset>>("assets/?limit=100")
      .then((d) => setAssets(d.results))
      .catch((e) => setError(e.message));
    if (!fresh)
      api<Script>("scripts/" + id + "/")
        .then(setForm)
        .catch((e) => setError(e.message));
  }, [id]);
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirty) e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
  function change(data: Partial<Script>) {
    setForm((f) => ({ ...f, ...data }));
    setDirty(true);
  }
  function update(index: number, data: Partial<Script["scenes"][number]>) {
    change({
      scenes: form.scenes.map((s, i) => (i === index ? { ...s, ...data } : s)),
    });
  }
  async function save() {
    setBusy(true);
    setError("");
    try {
      const d = await api<Script>(
        fresh ? "scripts/" : `scripts/${id}/`,
        fresh ? "POST" : "PUT",
        form,
      );
      setDirty(false);
      setForm(d);
      if (fresh) nav("/scripts/" + d.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Link to="/scripts">← 剧本列表</Link>
      <Heading
        title={fresh ? "写一个新故事" : form.title || "剧本编辑"}
        subtitle={`版本 ${form.revision} · ${form.scenes.length}/12 个分镜 · 总时长 ${form.scenes.reduce((a, s) => a + s.duration, 0)} / 60 秒`}
      >
        <button className="primary" disabled={busy} onClick={save}>
          {busy ? "保存中…" : dirty ? "保存修改" : "保存剧本"}
        </button>
        {!fresh && (
          <>
            <a className="button" href={`/api/scripts/${id}/export/`}>
              导出 Markdown
            </a>
            <button
              onClick={async () => {
                try {
                  const d = await api<Script>(
                    `scripts/${id}/duplicate/`,
                    "POST",
                    {},
                  );
                  nav("/scripts/" + d.id);
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              复制
            </button>
          </>
        )}
      </Heading>
      <ErrorBox error={error} />
      <div className="panel">
        <label>
          剧本标题
          <input
            required
            maxLength={160}
            value={form.title}
            onChange={(e) => change({ title: e.target.value })}
            placeholder="给故事起一个名字"
          />
        </label>
        <label>
          故事梗概
          <textarea
            maxLength={4000}
            rows={3}
            value={form.synopsis}
            onChange={(e) => change({ synopsis: e.target.value })}
          />
        </label>
      </div>
      <div className="section-title">
        <h2>分镜脚本</h2>
        <button
          disabled={form.scenes.length >= 12}
          onClick={() => change({ scenes: [...form.scenes, scene()] })}
        >
          ＋ 添加分镜
        </button>
      </div>
      {form.scenes.map((s, i) => (
        <section className="scene-editor" key={i}>
          <div className="scene-index">
            {String(i + 1).padStart(2, "0")}
            <span>SCENE</span>
          </div>
          <div className="scene-fields">
            <div className="form-row">
              <label>
                画面描述
                <textarea
                  maxLength={2000}
                  value={s.description}
                  onChange={(e) => update(i, { description: e.target.value })}
                />
              </label>
              <label>
                台词 / 字幕
                <textarea
                  maxLength={1000}
                  value={s.dialogue}
                  onChange={(e) => update(i, { dialogue: e.target.value })}
                />
              </label>
            </div>
            <div className="form-row three">
              <label>
                时长（秒）
                <input
                  type="number"
                  min={1}
                  max={60}
                  step={0.5}
                  value={s.duration}
                  onChange={(e) =>
                    update(i, { duration: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                画面素材
                <select
                  value={s.image_id || ""}
                  onChange={(e) =>
                    update(i, { image_id: Number(e.target.value) || null })
                  }
                >
                  <option value="">选择图片</option>
                  {assets
                    .filter((a) => a.kind === "image")
                    .map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                配音素材
                <select
                  value={s.audio_id || ""}
                  onChange={(e) =>
                    update(i, { audio_id: Number(e.target.value) || null })
                  }
                >
                  <option value="">无 / 使用 TTS</option>
                  {assets
                    .filter((a) => a.kind === "audio")
                    .map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                </select>
              </label>
            </div>
            <div className="actions">
              <button
                disabled={i === 0}
                onClick={() => {
                  const arr = [...form.scenes];
                  [arr[i - 1], arr[i]] = [arr[i], arr[i - 1]];
                  change({ scenes: arr });
                }}
              >
                上移
              </button>
              <button
                disabled={i === form.scenes.length - 1}
                onClick={() => {
                  const arr = [...form.scenes];
                  [arr[i + 1], arr[i]] = [arr[i], arr[i + 1]];
                  change({ scenes: arr });
                }}
              >
                下移
              </button>
              <button
                className="danger"
                disabled={form.scenes.length === 1}
                onClick={() =>
                  change({ scenes: form.scenes.filter((_, n) => n !== i) })
                }
              >
                删除分镜
              </button>
            </div>
          </div>
        </section>
      ))}
      {!fresh && (
        <div className="actions">
          <Link className="primary button" to={"/compose?script=" + id}>
            下一步 · 合成视频 →
          </Link>
          <button
            className="danger"
            onClick={async () => {
              if (confirm("删除此剧本？已提交任务的快照会保留。"))
                try {
                  await api(`scripts/${id}/`, "DELETE");
                  nav("/scripts");
                } catch (e) {
                  setError((e as Error).message);
                }
            }}
          >
            删除剧本
          </button>
        </div>
      )}
    </>
  );
}
