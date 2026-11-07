import type { Node, Edge, Viewport } from "@xyflow/react";

export type Data = {
  kind: string;
  label: string;
  text?: string;
  entity_id?: number;
  provider_id?: number;
  seconds?: number;
  size?: string;
  scene_index?: number;
  run_status?: string;
};
export type StudioNode = Node<Data>;
export type Document = { nodes: StudioNode[]; edges: Edge[]; viewport: Viewport };

export function referenceVoice(doc: Document, target: string): StudioNode | undefined {
  const incoming = doc.edges.filter((e) => e.target === target).map((e) => e.source);
  return doc.nodes.find((n) => incoming.includes(n.id) && n.data.kind === "tts");
}

export function configureReferenceVoice(
  doc: Document, target: string, patch: Partial<Data>, makeId: () => string,
): Document {
  const mix = doc.nodes.find((n) => n.id === target);
  if (!mix || !["tts", "voiceover"].includes(mix.data.kind)) throw Error("原配音节点已移除，音频仍保存在素材库");
  if (mix.data.kind === "tts") return {
    ...doc, nodes: doc.nodes.map((n) => n.id === target ? {...n, data: {...n.data, ...patch}} : n),
  };
  const incomingTts = doc.edges.filter((e) => e.target === target && doc.nodes.some((n) => n.id === e.source && n.data.kind === "tts"));
  if (incomingTts.length > 1) throw Error("此合成节点连接了多个AI配音，请先保留一个配音输入");
  const existing = referenceVoice(doc, target);
  if (!existing && doc.nodes.length >= 100) throw Error("画布已满，请先移除不用的节点，再添加参考音色配音");
  const ident = existing?.id || makeId();
  const voice: StudioNode = existing ? {...existing, data: {...existing.data, ...patch}} : {
    id: ident, type: "studio", position: {x: Math.max(-100000, mix.position.x - 320), y: Math.min(100000, mix.position.y + 230)},
    data: {kind: "tts", label: "AI配音 · 参考音色", ...patch},
  };
  const nodes = existing ? doc.nodes.map((n) => n.id === ident ? voice : n) : [...doc.nodes, voice];
  // Replace this mixer's audio input; retain the previous nodes and all other connections.
  const edges = doc.edges.filter((e) => e.target !== target || !doc.nodes.some((n) => n.id === e.source && ["audio", "tts"].includes(n.data.kind)));
  edges.push({id: makeId(), source: ident, target});
  if (!existing) {
    // Reuse a connected story/scene for its dialogue, without connecting a script to an audio asset.
    const ancestors = new Set<string>([target]);
    for (let changed = true; changed;) {
      changed = false;
      for (const e of doc.edges) if (ancestors.has(e.target) && !ancestors.has(e.source)) {
        ancestors.add(e.source); changed = true;
      }
    }
    const story = doc.nodes.find((n) => ancestors.has(n.id) && ["llm", "scene"].includes(n.data.kind));
    if (story) edges.push({id: makeId(), source: story.id, target: ident});
  }
  if (edges.length > 200) throw Error("连线数量超过200，请先整理画布");
  return {...doc, nodes, edges};
}
