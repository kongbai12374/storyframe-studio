import { describe, it, expect } from "vitest";
import { configureReferenceVoice, referenceVoice, type Document } from "./audioGraph";
let seq = 0;
const key = () => `new-${++seq}`;
function graph(): Document {
  return {
    nodes: ["story", "audio", "video", "mix", "result"].map((id) => ({id, type: "studio", position: {x: 0, y: 0}, data: {kind: ({story: "llm", video: "video_api", mix: "voiceover"} as Record<string,string>)[id] || id, label: id}})),
    edges: [["story", "video"], ["video", "mix"], ["audio", "mix"], ["mix", "result"]].map(([source, target]) => ({id: `${source}-${target}`, source, target})),
    viewport: {x: 0, y: 0, zoom: 1},
  };
}
describe("reference voice graph", () => {
  it("adds a TTS input, preserves the original asset and video, and reuses the connected story", () => {
    const before = graph();
    const after = configureReferenceVoice(before, "mix", {entity_id: 8, provider_id: 2}, key);
    const tts = referenceVoice(after, "mix")!;
    expect(tts.data.entity_id).toBe(8);
    expect(tts.data.provider_id).toBe(2);
    expect(after.nodes.find((n) => n.id === "audio")).toEqual(before.nodes[1]);
    expect(after.edges.some((e) => e.source === "audio" && e.target === "mix")).toBe(false);
    expect(after.edges.some((e) => e.source === "video" && e.target === "mix")).toBe(true);
    expect(after.edges.some((e) => e.source === "story" && e.target === tts.id)).toBe(true);
    expect(before.nodes).toHaveLength(5);
    expect(before.edges).toHaveLength(4);
  });
  it("reuses the same TTS node and never duplicates the mix connection", () => {
    const first = configureReferenceVoice(graph(), "mix", {entity_id: 8}, key);
    const second = configureReferenceVoice(first, "mix", {entity_id: 9, text: "new words"}, key);
    expect(second.nodes).toHaveLength(6);
    expect(referenceVoice(second, "mix")!.data).toMatchObject({entity_id: 9, text: "new words"});
    expect(second.edges.filter((e) => e.target === "mix")).toHaveLength(2);
    expect(new Set(second.edges.map((e) => `${e.source}:${e.target}`)).size).toBe(second.edges.length);
  });
  it("updates the captured original TTS node when the selection changes during upload", () => {
    const doc = configureReferenceVoice(graph(), "mix", {}, key);
    const tts = referenceVoice(doc, "mix")!;
    const next = configureReferenceVoice(doc, tts.id, {entity_id: 99}, key);
    expect(referenceVoice(next, "mix")!.data.entity_id).toBe(99);
    expect(next.nodes.find((n) => n.id === "mix")!.data.entity_id).toBeUndefined();
    expect(() => configureReferenceVoice(next, "deleted", {entity_id: 99}, key)).toThrow("原配音节点已移除");
  });
});
