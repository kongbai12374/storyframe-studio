import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  Handle,
  Position,
  type Connection,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, Asset, Page, Script, Job, key } from "../../../api";
import { ErrorBox } from "../../../components";
import AudioPicker from "./AudioPicker";
import { configureReferenceVoice, referenceVoice, type Data, type StudioNode, type Document } from "./audioGraph";

type Project = {
  id: number;
  name: string;
  revision: number;
  document: Document;
  latest_job_id?: number | null;
};
const kinds: Record<string, { label: string; icon: string }> = {
  script: { label: "剧本", icon: "▤" },
  scene: { label: "分镜", icon: "▥" },
  image: { label: "图片素材", icon: "▧" },
  image_api: { label: "AI 分镜生图", icon: "✧" },
  voiceover: { label: "配音合成", icon: "♫" },
  audio: { label: "音频素材", icon: "♫" },
  compose: { label: "本地合成", icon: "▶" },
  video_api: { label: "API 视频生成", icon: "✦" },
  result: { label: "结果预览", icon: "◉" },
  note: { label: "便签", icon: "✎" },
  llm: { label: "AI 剧本", icon: "✦" },
  tts: { label: "AI 配音", icon: "♬" },
};
function StudioCard({ data, selected }: NodeProps<StudioNode>) {
  return (
    <div className={"studio-node " + data.kind + (selected ? " chosen" : "")}>
      <Handle type="target" position={Position.Left} />
      <div className="node-kind">
        <span>{kinds[data.kind]?.icon}</span>
        {kinds[data.kind]?.label}
      </div>
      <strong>{data.label}</strong>
      {data.kind === "image" && data.entity_id && (
        <img
          draggable={false}
          src={`/api/assets/${data.entity_id}/file/?thumbnail=1`}
          alt={data.label}
          style={{
            width: "100%",
            height: 100,
            objectFit: "cover",
            borderRadius: 6,
            marginTop: 8,
          }}
        />
      )}
      <p>
        {data.text?.slice(0, 60) ||
          (data.entity_id ? "已关联 #" + data.entity_id : "点击节点配置内容")}
      </p>
      {["llm", "tts", "video_api", "image_api"].includes(data.kind) && (
        <small>执行时使用已配置的服务</small>
      )}
      {data.run_status && (
        <small className="node-run-status">
          {data.run_status === "completed"
            ? "✓ 已完成"
            : data.run_status === "failed"
              ? "✕ 失败"
              : "执行中"}
        </small>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
const nodeTypes = { studio: StudioCard };
export function cleanDocument(doc: Document): Document {
  return {
    nodes: doc.nodes.map((n) => ({
      id: n.id,
      type: "studio",
      position: n.position,
      data: n.data,
    })),
    edges: doc.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
    })),
    viewport: doc.viewport,
  };
}
export default function Canvas() {
  const [videoProviders, setVideoProviders] = useState<
    { id: number; name: string; active: boolean; service: string }[]
  >([]);
  const { id } = useParams(),
    nav = useNavigate();
  const [loaded, setLoaded] = useState(false),
    [name, setName] = useState(""),
    [doc, setDoc] = useState<Document>({
      nodes: [],
      edges: [],
      viewport: { x: 0, y: 0, zoom: 1 },
    }),
    [selected, setSelected] = useState<string | null>(null),
    [error, setError] = useState(""),
    [saveState, setSaveState] = useState("已保存"),
    [dirty, setDirty] = useState(false),
    [assets, setAssets] = useState<Asset[]>([]),
    [scripts, setScripts] = useState<Script[]>([]),
    [listMode, setListMode] = useState(false),
    [job, setJob] = useState<Job | null>(null),
    [submitting, setSubmitting] = useState(false),
    [budgetLimit, setBudgetLimit] = useState("3"),
    [uploadingAudio, setUploadingAudio] = useState(false);
  const current = useRef(doc),
    title = useRef(name),
    revision = useRef(1),
    generation = useRef(0),
    savedGeneration = useRef(0),
    saving = useRef<Promise<void> | null>(null),
    history = useRef<Document[]>([]),
    future = useRef<Document[]>([]),
    instance = useRef<ReactFlowInstance<StudioNode> | null>(null),
    conflict = useRef(false);
  current.current = doc;
  title.current = name;
  const load = useCallback(async () => {
    try {
      const p = await api<Project>(`canvases/${id}/`);
      setName(p.name);
      title.current = p.name;
      setDoc(p.document);
      current.current = p.document;
      revision.current = p.revision;
      generation.current = 0;
      savedGeneration.current = 0;
      history.current = [];
      future.current = [];
      conflict.current = false;
      setDirty(false);
      setSaveState("已保存");
      setError("");
      setLoaded(true);
      if (p.latest_job_id) setJob(await api<Job>(`jobs/${p.latest_job_id}/`));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);
  useEffect(() => {
    load();
    api<{ id: number; name: string; service: string; active: boolean }[]>(
      "providers/",
    )
      .then((r) => setVideoProviders(r.filter((p) => p.active)))
      .catch((e) => setError(e.message));
    api<Page<Asset>>("assets/?limit=100")
      .then((r) => setAssets(r.results))
      .catch((e) => setError(e.message));
    api<Page<Script>>("scripts/?limit=100")
      .then((r) => setScripts(r.results))
      .catch((e) => setError(e.message));
  }, [load]);
  function mutate(next: Document, record = true) {
    if (record) {
      history.current.push(structuredClone(current.current));
      if (history.current.length > 50) history.current.shift();
      future.current = [];
    }
    generation.current++;
    current.current = next;
    setDoc(next);
    setDirty(true);
    setSaveState("尚未保存");
  }
  async function save() {
    if (saving.current) await saving.current;
    if (generation.current === savedGeneration.current) return;
    if (conflict.current) throw Error("存在版本冲突，请重新载入或另存副本");
    const at = generation.current,
      snapshot = cleanDocument(current.current);
    setSaveState("保存中…");
    const promise = (async () => {
      try {
        const p = await api<Project>(`canvases/${id}/`, "PUT", {
          name: title.current,
          revision: revision.current,
          document: snapshot,
        });
        revision.current = p.revision;
        savedGeneration.current = at;
        if (generation.current === at) {
          setDirty(false);
          setSaveState("已保存");
        } else setSaveState("尚未保存");
      } catch (e) {
        setError((e as Error).message);
        setSaveState("保存失败");
        if ((e as Error).message.includes("其他页面")) conflict.current = true;
        throw e;
      }
    })();
    saving.current = promise;
    try {
      await promise;
    } finally {
      saving.current = null;
    }
  }
  useEffect(() => {
    if (!dirty || !loaded) return;
    const timer = setTimeout(() => save().catch(() => {}), 1000);
    return () => clearTimeout(timer);
  }, [doc, name, dirty, loaded]);
  useEffect(() => {
    function unload(e: BeforeUnloadEvent) {
      if (generation.current !== savedGeneration.current) e.preventDefault();
    }
    function click(e: MouseEvent) {
      const a = (e.target as HTMLElement).closest("a");
      if (
        a &&
        a.pathname !== location.pathname &&
        generation.current !== savedGeneration.current &&
        !confirm("画布尚未保存，仍要离开吗？")
      ) {
        e.preventDefault();
        e.stopPropagation();
      }
    }
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", click, true);
    return () => {
      window.removeEventListener("beforeunload", unload);
      document.removeEventListener("click", click, true);
    };
  }, []);
  useEffect(() => {
    if (!job || !["queued", "running", "cancel_requested"].includes(job.status))
      return;
    let live = true;
    const timer = setTimeout(
      () =>
        api<Job>(`jobs/${job.id}/`)
          .then((j) => {
            if (live) setJob(j);
          })
          .catch((e) => {
            if (live) setError(e.message);
          }),
      document.hidden ? 15000 : 3000,
    );
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [job]);
  function add(kind: string) {
    if (doc.nodes.length >= 100) {
      setError("最多100个节点");
      return;
    }
    const n: StudioNode = {
      id: key(),
      type: "studio",
      position: {
        x: 100 + (doc.nodes.length % 4) * 280,
        y: 100 + Math.floor(doc.nodes.length / 4) * 190,
      },
      data: { kind, label: kinds[kind].label },
    };
    mutate({ ...doc, nodes: [...doc.nodes, n] });
    setSelected(n.id);
  }
  function undo() {
    const previous = history.current.pop();
    if (previous) {
      future.current.push(structuredClone(doc));
      mutate(previous, false);
    }
  }
  function redo() {
    const next = future.current.pop();
    if (next) {
      history.current.push(structuredClone(doc));
      mutate(next, false);
    }
  }
  function update(data: Partial<Data>) {
    mutate({
      ...doc,
      nodes: doc.nodes.map((n) =>
        n.id === selected ? { ...n, data: { ...n.data, ...data } } : n,
      ),
    });
  }
  function configureVoice(target: string, patch: Partial<Data>) {
    try {
      mutate(configureReferenceVoice(current.current, target, patch, key));
      setError("");
    } catch (e) { setError((e as Error).message); }
  }
  function acceptReference(target: string, asset: Asset) {
    setAssets((items) => [asset, ...items.filter((a) => a.id !== asset.id)]);
    const targetNode = current.current.nodes.find((n) => n.id === target);
    const existing = targetNode?.data.kind === "tts" ? targetNode : referenceVoice(current.current, target);
    configureVoice(target, {
      entity_id: asset.id,
      ...(!existing?.data.provider_id ? {provider_id: videoProviders.find((p) => p.service === "tts")?.id} : {}),
    });
  }
  function removeSelected() {
    if (!selected) return;
    mutate({
      ...doc,
      nodes: doc.nodes.filter((n) => n.id !== selected),
      edges: doc.edges.filter(
        (e) => e.source !== selected && e.target !== selected,
      ),
    });
    setSelected(null);
  }
  const executing = Boolean(
    job && ["queued", "running", "cancel_requested"].includes(job.status),
  );
  async function execute(only = false) {
    if (uploadingAudio) { setError("请等待参考音频上传完成后再执行"); return; }
    if (executing || submitting) {
      setError("当前流程尚未结束，请等待完成或先取消，避免重复收费");
      return;
    }
    if (
      doc.nodes.some((n) =>
        ["video_api", "image_api", "tts", "llm"].includes(n.data.kind),
      ) &&
      !confirm(
        "执行将调用图中配置的AI服务并可能收费。预算按已核对单价保守预留；已完成节点会保留。是否继续？",
      )
    )
      return;
    setSubmitting(true);
    setError("");
    try {
      await save();
      if (generation.current !== savedGeneration.current)
        throw Error("请等待最新修改保存后执行");
      const j = await api<Job>(`canvases/${id}/run/`, "POST", {
        revision: revision.current,
        idempotency_key: key(),
        confirm_paid: true,
        ...(doc.nodes.some((n) =>
          ["image_api", "voiceover"].includes(n.data.kind),
        )
          ? { budget_limit_yuan: Number(budgetLimit) }
          : {}),
        ...(only && selected
          ? { selected: [selected] }
          : doc.nodes.some((n) => n.data.kind === "result")
            ? {
                selected: doc.nodes
                  .filter((n) => n.data.kind === "result")
                  .map((n) => n.id),
              }
            : {}),
      });
      setJob(j);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }
  const node = doc.nodes.find((n) => n.id === selected),
    available =
      node && ["image", "audio", "tts"].includes(node.data.kind)
        ? assets.filter((a) =>
            node.data.kind === "tts"
              ? a.kind === "audio"
              : a.kind === node.data.kind,
          )
        : scripts;
  const voice = node?.data.kind === "tts" ? node : node?.data.kind === "voiceover" ? referenceVoice(doc, node.id) : undefined;
  return (
    <div className="canvas-workspace">
      <div className="canvas-top">
        <div>
          <Link to="/canvases">← 创作画布</Link>
          <input
            disabled={!loaded}
            aria-label="画布名称"
            value={name}
            maxLength={160}
            onChange={(e) => {
              setName(e.target.value);
              generation.current++;
              setDirty(true);
            }}
          />
          <span className={"save-state " + (dirty ? "pending" : "")}>
            {saveState}
          </span>
        </div>
        <div className="actions">
          <button onClick={() => setListMode(!listMode)}>
            {listMode ? "画布模式" : "列表模式"}
          </button>
          <button onClick={() => save().catch(() => {})}>保存</button>
          <button
            className="primary"
            disabled={submitting || executing || uploadingAudio}
            onClick={() => execute(false)}
          >
            {submitting ? "提交中…" : executing ? "流程执行中…" : "▶ 执行流程"}
          </button>
        </div>
      </div>
      <ErrorBox error={error} />
      {error && (
        <div className="actions">
          <button
            onClick={() => {
              if (!dirty || confirm("重新载入会丢弃当前未保存修改，确定继续？"))
                load();
              api<
                { id: number; name: string; service: string; active: boolean }[]
              >("providers/")
                .then((r) =>
                  setVideoProviders(
                    r.filter((p) => p.service === "video" && p.active),
                  ),
                )
                .catch((e) => setError(e.message));
            }}
          >
            重新载入
          </button>
          <button
            onClick={async () => {
              try {
                const p = await api<Project>("canvases/", "POST", {
                  name: name + " 副本",
                });
                await api(`canvases/${p.id}/`, "PUT", {
                  revision: p.revision,
                  name: p.name,
                  document: cleanDocument(doc),
                });
                nav("/creator/canvas/" + p.id);
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            另存副本
          </button>
        </div>
      )}
      <div className="canvas-body">
        <div className="node-palette">
          <p className="nav-label">添加节点</p>
          {Object.entries(kinds).map(([kind, v]) => (
            <button key={kind} disabled={!loaded} onClick={() => add(kind)}>
              <span>{v.icon}</span>
              {v.label}
            </button>
          ))}
          <hr />
          <button onClick={undo}>↶ 撤销</button>
          <button onClick={redo}>↷ 重做</button>
          <p className="muted small">连线整理思路，点击执行后才会运行。</p>
        </div>
        <div className="canvas-stage">
          {loaded &&
            (listMode ? (
              <div className="canvas-list">
                {doc.nodes.map((n) => (
                  <button
                    className={selected === n.id ? "selected" : ""}
                    key={n.id}
                    onClick={() => setSelected(n.id)}
                  >
                    <span>
                      {kinds[n.data.kind].icon} {kinds[n.data.kind].label}
                    </span>
                    <strong>{n.data.label}</strong>
                  </button>
                ))}
                {!doc.nodes.length && <p>点击左侧按钮添加第一个节点。</p>}
              </div>
            ) : (
              <ReactFlow<StudioNode>
                nodes={doc.nodes.map((n) => ({
                  ...n,
                  selected: n.id === selected,
                  data: { ...n.data, run_status: job?.node_statuses?.[n.id] },
                }))}
                edges={doc.edges}
                nodeTypes={nodeTypes}
                defaultViewport={doc.viewport}
                minZoom={0.1}
                maxZoom={4}
                onInit={(i) => {
                  instance.current = i;
                }}
                onNodeClick={(_, n) => setSelected(n.id)}
                onPaneClick={() => setSelected(null)}
                onNodesChange={(changes) => {
                  const base = current.current;
                  const next = applyNodeChanges(changes, base.nodes);
                  if (
                    changes.some(
                      (c) => !["select", "dimensions"].includes(c.type),
                    )
                  )
                    mutate(
                      {
                        ...base,
                        nodes: next,
                        edges: base.edges.filter(
                          (e) =>
                            next.some((n) => n.id === e.source) &&
                            next.some((n) => n.id === e.target),
                        ),
                      },
                      !changes.some((c) => c.type === "position" && c.dragging),
                    );
                  else setDoc((d) => ({ ...d, nodes: next }));
                }}
                onEdgesChange={(changes) => {
                  if (changes.some((c) => c.type !== "select"))
                    mutate({
                      ...current.current,
                      edges: applyEdgeChanges(changes, current.current.edges),
                    });
                }}
                onConnect={(c: Connection) =>
                  mutate({
                    ...current.current,
                    edges: addEdge({ ...c, id: key() }, current.current.edges),
                  })
                }
                onMoveEnd={(_, v) => {
                  if (JSON.stringify(v) !== JSON.stringify(doc.viewport))
                    mutate({ ...doc, viewport: v }, false);
                }}
                deleteKeyCode={["Backspace", "Delete"]}
                selectionOnDrag
              >
                <Background gap={22} color="#dce4e3" />
                <Controls />
                <MiniMap pannable zoomable nodeColor="#b8c9c2" />
                {!doc.nodes.length && (
                  <div className="canvas-empty">
                    <span>⌘</span>
                    <h2>给想法一个展开的地方</h2>
                    <p>
                      从左侧添加剧本、素材和视频合成节点，连接你的创作流程。
                    </p>
                  </div>
                )}
              </ReactFlow>
            ))}
        </div>
        <div className="property-panel">
          {node ? (
            <>
              <p className="eyebrow">NODE PROPERTIES</p>
              <h3>{kinds[node.data.kind].label}</h3>
              <label>
                节点名称
                <input
                  maxLength={160}
                  value={node.data.label}
                  onChange={(e) => update({ label: e.target.value })}
                />
              </label>
              {!["note", "llm", "image_api", "voiceover", "tts"].includes(
                node.data.kind,
              ) && (
                <label>
                  {node.data.kind === "tts" ? "参考音频" : "关联内容"}
                  <select
                    value={node.data.entity_id || ""}
                    onChange={(e) =>
                      update({ entity_id: Number(e.target.value) || undefined })
                    }
                  >
                    <option value="">不关联 / 从连线输入</option>
                    {available.map((a) => (
                      <option key={a.id} value={a.id}>
                        {"name" in a ? a.name : a.title}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {["tts", "voiceover"].includes(node.data.kind) && (
                <>
                  <AudioPicker key={node.id} label="参考音频（音色）" assets={assets}
                    value={voice?.data.entity_id} disabled={executing || submitting || uploadingAudio}
                    onBusyChange={setUploadingAudio}
                    onSelect={(entity_id) => configureVoice(node.id, {entity_id})}
                    onUploaded={(asset) => acceptReference(node.id, asset)} />
                  <label>配音 API 服务
                    <select value={voice?.data.provider_id || ""} disabled={executing || submitting || uploadingAudio}
                      onChange={(e) => configureVoice(node.id, {provider_id: Number(e.target.value) || undefined})}>
                      <option value="">选择已启用的配音服务</option>
                      {videoProviders.filter((p) => p.service === "tts").map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                  </label>
                  <p className="muted small">参考音频用于模仿音色，上传后不会直接作为成片旁白播放。点击执行才会调用配音服务；留空文本时读取连接剧本的台词。</p>
                  {node.data.kind === "voiceover" && <>
                    <label>配音文本<textarea rows={4} maxLength={500} value={voice?.data.text || ""}
                      disabled={executing || submitting || uploadingAudio} placeholder="输入希望用参考音色朗读的内容，或留空使用剧本台词"
                      onChange={(e) => configureVoice(node.id, {text: e.target.value})} /></label>
                    {!voice && <p className="muted small">上传或选择参考音频后，将自动添加并连接AI配音节点，替换当前合成的音频输入，原素材保留。</p>}
                  </>}
                </>
              )}
              {node.data.kind === "image_api" && (
                <label>图片 API 服务
                  <select value={node.data.provider_id || ""} onChange={(e) => update({provider_id: Number(e.target.value) || undefined})}>
                    <option value="">选择已启用服务</option>
                    {videoProviders.filter((p) => p.service === "image").map((p) => <option value={p.id} key={p.id}>{p.name}</option>)}
                  </select>
                </label>
              )}
              {node.data.kind === "image_api" && (
                <>
                  <label>
                    分镜序号
                    <input
                      type="number"
                      min={1}
                      max={12}
                      value={node.data.scene_index || 1}
                      onChange={(e) =>
                        update({ scene_index: Number(e.target.value) })
                      }
                    />
                  </label>
                  <label>
                    图片尺寸
                    <input
                      value={node.data.size || "2048x2048"}
                      onChange={(e) => update({ size: e.target.value })}
                    />
                  </label>
                  <p className="muted small">
                    从连接的AI剧本读取此分镜，每个节点生成1张图片。下方备注可填写统一角色外观。
                  </p>
                </>
              )}
              {node.data.kind === "tts" && (
                <p className="muted small">
                  留空配音文本时读取连接剧本的台词。IndexTTS2需选择参考音频，并配置工作流映射。
                </p>
              )}
              {node.data.kind === "voiceover" && (
                <label>
                  成片时长（秒）
                  <input
                    type="number"
                    min={1}
                    max={60}
                    value={node.data.seconds || 10}
                    onChange={(e) =>
                      update({ seconds: Number(e.target.value) })
                    }
                  />
                  <span className="muted small">
                    连接API视频与AI配音输出，合成为带配音的视频。上传参考音频后可在这里配置新的配音。
                  </span>
                </label>
              )}
              {node.data.kind === "video_api" && (
                <>
                  <label>
                    视频 API 服务
                    <select
                      value={node.data.provider_id || ""}
                      onChange={(e) =>
                        update({
                          provider_id: Number(e.target.value) || undefined,
                        })
                      }
                    >
                      <option value="">选择已启用的视频API</option>
                      {videoProviders
                        .filter((p) => p.service === "video")
                        .map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    生成时长（秒）
                    <input
                      type="number"
                      min={1}
                      max={60}
                      value={node.data.seconds || 5}
                      onChange={(e) =>
                        update({ seconds: Number(e.target.value) })
                      }
                    />
                  </label>
                  <label>
                    画面方向
                    <select
                      value={node.data.size || "1280x720"}
                      onChange={(e) => update({ size: e.target.value })}
                    >
                      <option value="1280x720">横屏 1280×720</option>
                      <option value="720x1280">竖屏 720×1280</option>
                    </select>
                  </label>
                  <p className="muted small">
                    填写下方提示词或连接剧本。可连接最多9个图片节点作为参考图，按连线创建顺序发送；需在请求模板启用
                    images_data_urls、images_base64 或 image_url_0 等
                    数组占位符。实际时长和模型能力由供应商决定。
                  </p>
                </>
              )}
              <label>
                {node.data.kind === "llm"
                  ? "故事梗概"
                  : node.data.kind === "tts"
                    ? "配音文本"
                    : "备注"}
                <textarea
                  rows={5}
                  maxLength={node.data.kind === "tts" ? 500 : 4000}
                  value={node.data.text || ""}
                  onChange={(e) => update({ text: e.target.value })}
                />
              </label>
              {node.data.kind === "image" && node.data.entity_id && (
                <img
                  className="property-image"
                  src={`/api/assets/${node.data.entity_id}/file/?thumbnail=1`}
                  alt="关联图片"
                />
              )}
              {node.data.kind === "audio" && node.data.entity_id && (
                <audio
                  controls
                  preload="none"
                  src={`/api/assets/${node.data.entity_id}/file/`}
                />
              )}
              <p className="muted small">
                输入连线 {doc.edges.filter((e) => e.target === selected).length}{" "}
                · 输出连线{" "}
                {doc.edges.filter((e) => e.source === selected).length}
              </p>
              <div className="property-actions">
                <button
                  disabled={submitting || executing || uploadingAudio}
                  onClick={() => execute(true)}
                >
                  执行此节点及依赖
                </button>
                <button
                  onClick={() => {
                    const clone = {
                      ...node,
                      id: key(),
                      position: {
                        x: node.position.x + 40,
                        y: node.position.y + 50,
                      },
                      data: { ...node.data, label: node.data.label + " 副本" },
                    };
                    mutate({ ...doc, nodes: [...doc.nodes, clone] });
                    setSelected(clone.id);
                  }}
                >
                  复制节点
                </button>
                <button className="danger" onClick={removeSelected}>
                  删除节点
                </button>
                {doc.edges
                  .filter((e) => e.source === selected || e.target === selected)
                  .map((e) => (
                    <button
                      key={e.id}
                      onClick={() =>
                        mutate({
                          ...doc,
                          edges: doc.edges.filter((x) => x.id !== e.id),
                        })
                      }
                    >
                      断开 {e.source === selected ? "输出" : "输入"}连线
                    </button>
                  ))}
              </div>
            </>
          ) : (
            <>
              <p className="eyebrow">STUDIO CANVAS</p>
              <h3>你的创作全景</h3>
              <p className="muted">选择节点编辑属性，拖动端点连接流程。</p>
              <div className="canvas-help">
                剧本 → 视频合成 → 结果
                <br />
                图片 → 视频合成
                <br />
                音频 → 视频合成
              </div>
              <Link to="/settings">配置 AI 服务 ↗</Link>
            </>
          )}
          {job && (
            <section className="canvas-job">
              <h3>流程 #{job.id}</h3>
              {job.budget_status && (
                <p className="muted small">
                  费用预留 ¥{job.budget_status.reserved_yuan} / 预算 ¥
                  {job.budget_status.limit_yuan || "未设置"}（实际以账单为准）
                </p>
              )}
              {job.result.asset_ids instanceof Array && (
                <div className="reference-grid">
                  {(job.result.asset_ids as number[]).map((id) => (
                    <img
                      key={id}
                      src={`/api/assets/${id}/file/?thumbnail=1`}
                      alt="生成分镜"
                      style={{ maxWidth: "100%" }}
                    />
                  ))}
                </div>
              )}
              <p>{job.stage}</p>
              <div className="progress-track">
                <div style={{ width: job.progress + "%" }} />
              </div>
              <ErrorBox error={job.error} />
              {job.download_url && (
                <>
                  <video controls preload="none" src={job.download_url} />
                  <a href={job.download_url + "?download=1"}>下载成片 ↓</a>
                </>
              )}
              {["failed", "interrupted", "cancelled"].includes(job.status) && (
                <button
                  disabled={submitting || executing || uploadingAudio}
                  onClick={async () => {
                    if (
                      !confirm(
                        "继续未完成流程会跳过已完成节点，后续API可能收费，继续沿用原预算。确认已修复配置并继续？",
                      )
                    )
                      return;
                    setSubmitting(true);
                    setError("");
                    try {
                      setJob(
                        await api<Job>(`jobs/${job.id}/retry/`, "POST", {
                          confirm_paid: true,
                          idempotency_key: `resume-canvas-job:${job.id}`,
                        }),
                      );
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setSubmitting(false);
                    }
                  }}
                >
                  继续未完成流程
                </button>
              )}
              <Link to={"/jobs/" + job.id}>查看日志与节点结果 →</Link>
              {["running", "queued"].includes(job.status) && (
                <button
                  onClick={async () => {
                    try {
                      setJob(
                        await api<Job>(`jobs/${job.id}/cancel/`, "POST", {}),
                      );
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  取消流程
                </button>
              )}
            </section>
          )}
        </div>
      </div>
      <div className="canvas-footer">
        <span>
          {doc.nodes.length} / 100 节点 · {doc.edges.length} / 200 连线
        </span>
        {doc.nodes.some((n) =>
          ["image_api", "voiceover"].includes(n.data.kind),
        ) && (
          <label
            style={{ display: "flex", gap: 8, alignItems: "center", margin: 0 }}
          >
            预算上限（元）
            <input
              aria-label="画布预算上限"
              type="number"
              min="0.01"
              max="100"
              step="0.01"
              value={budgetLimit}
              onChange={(e) => setBudgetLimit(e.target.value)}
              style={{ width: 70, padding: 4 }}
            />
          </label>
        )}
        <span>自动保存 · 串行执行 · 素材私有</span>
      </div>
    </div>
  );
}
