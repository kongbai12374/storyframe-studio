import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import AudioPicker from "./AudioPicker";
import { api, type Asset } from "../../../api";
vi.mock("../../../api", () => ({api: vi.fn()}));
afterEach(() => {cleanup(); vi.resetAllMocks();});
const asset = {id: 8, name: "reference.wav", kind: "audio"} as Asset;
function setup() {
  const onUploaded = vi.fn(), onBusyChange = vi.fn();
  render(<AudioPicker label="参考音频（音色）" assets={[]} onSelect={vi.fn()} onUploaded={onUploaded} onBusyChange={onBusyChange} />);
  return {input: screen.getByLabelText("上传参考音频（音色）"), onUploaded, onBusyChange};
}
it("uploads a reference through the asset endpoint and auto-associates the result", async () => {
  vi.mocked(api).mockResolvedValue(asset);
  const {input, onUploaded, onBusyChange} = setup();
  fireEvent.change(input, {target: {files: [new File(["wav"], "reference.wav", {type: "audio/wav"})]}});
  await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(asset));
  expect(api).toHaveBeenCalledTimes(1);
  const [path, method, form] = vi.mocked(api).mock.calls[0];
  expect([path, method]).toEqual(["assets/", "POST"]);
  expect((form as FormData).get("file")).toBeInstanceOf(File);
  expect(onBusyChange.mock.calls).toEqual([[true], [false]]);
});
it("rejects image files before any upload or generation", () => {
  const {input} = setup();
  fireEvent.change(input, {target: {files: [new File(["png"], "image.png")]}});
  expect(screen.getByRole("alert").textContent).toContain("WAV 或 MP3");
  expect(api).not.toHaveBeenCalled();
});
it("reports backend validation failure and permits retry without replacing the reference", async () => {
  vi.mocked(api).mockRejectedValueOnce(new Error("音频最长60秒"));
  const {input, onUploaded} = setup();
  fireEvent.change(input, {target: {files: [new File(["wav"], "long.wav")]}});
  await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("音频最长60秒"));
  expect(onUploaded).not.toHaveBeenCalled();
  vi.mocked(api).mockResolvedValueOnce(asset);
  fireEvent.change(input, {target: {files: [new File(["wav"], "reference.wav")]}});
  await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(asset));
});

it("rejects audio over 20MB without sending the file", () => {
  const {input} = setup();
  const file = new File(["wav"], "large.wav");
  Object.defineProperty(file, "size", {value: 20 * 1024 * 1024 + 1});
  fireEvent.change(input, {target: {files: [file]}});
  expect(screen.getByRole("alert").textContent).toContain("20MB");
  expect(api).not.toHaveBeenCalled();
});
