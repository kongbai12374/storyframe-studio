import { useRef, useState } from "react";
import { api, type Asset } from "../../../api";

type Props = {
  label: string;
  assets: Asset[];
  value?: number;
  disabled?: boolean;
  onSelect: (id?: number) => void;
  onUploaded: (asset: Asset) => void;
  onBusyChange: (busy: boolean) => void;
};

export default function AudioPicker({ label, assets, value, disabled, onSelect, onUploaded, onBusyChange }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const uploading = useRef(false);
  const audio = assets.filter((a) => a.kind === "audio");
  async function upload(file?: File) {
    if (!file || uploading.current || disabled) return;
    setError("");
    if (!/\.(wav|mp3)$/i.test(file.name)) {
      setError("请选择 WAV 或 MP3 音频");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      setError("音频不能超过20MB");
      return;
    }
    uploading.current = true;
    setBusy(true);
    onBusyChange(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("tags", "画布配音");
      const asset = await api<Asset>("assets/", "POST", form);
      if (asset.kind !== "audio") throw Error("上传的文件不是有效音频");
      onUploaded(asset);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      uploading.current = false;
      setBusy(false);
      onBusyChange(false);
    }
  }
  return (
    <div className="canvas-audio-picker">
      <label>{label}
        <select value={value || ""} disabled={disabled || busy}
          onChange={(e) => { setError(""); onSelect(Number(e.target.value) || undefined); }}>
          <option value="">选择素材库音频 / 上传新音频</option>
          {value && !audio.some((a) => a.id === value) && <option value={value}>已关联音频 #{value}</option>}
          {audio.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </label>
      <label>上传{label}
        <input type="file" accept=".wav,.mp3,audio/wav,audio/x-wav,audio/mpeg"
          disabled={disabled || busy} onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            void upload(file);
          }} />
      </label>
      <p className="muted small" role="status">{busy ? "正在上传并校验音频…" : "WAV / MP3，最大20MB、最长60秒。上传后自动关联，也会保存在素材库。"}</p>
      {error && <p role="alert">{error}</p>}
      {value && <audio key={value} controls preload="none" aria-label={`${label}试听`} src={`/api/assets/${value}/file/`} />}
    </div>
  );
}
