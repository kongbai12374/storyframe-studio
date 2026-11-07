import { useEffect, useState } from "react";
import { api } from "./api";

export function useDeletion(
  path: string,
  items: { id: number }[],
  reload: () => void,
  note: string,
  scope: string | number,
) {
  const [selected, setSelected] = useState<number[]>([]),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  useEffect(() => {
    setSelected([]);
    setMessage("");
  }, [scope]);
  const available = selected.filter((id) =>
    items.some((item) => item.id === id),
  );
  async function remove(ids: number[]) {
    if (
      !ids.length ||
      busy ||
      !confirm(`确认永久删除这 ${ids.length} 项？${note}`)
    )
      return;
    setBusy(true);
    setMessage("");
    let removed = 0;
    const failures: string[] = [];
    try {
      for (const id of ids) {
        try {
          await api(`${path}/${id}/`, "DELETE");
          removed++;
        } catch (e) {
          failures.push(`#${id}：${(e as Error).message}`);
        }
      }
      setSelected([]);
      setMessage(`已删除 ${removed} 项。${failures.join("；")}`);
      reload();
    } finally {
      setBusy(false);
    }
  }
  return {
    remove,
    checkbox: (id: number) => (
      <input
        type="checkbox"
        aria-label={`选择 #${id}`}
        disabled={busy}
        checked={available.includes(id)}
        onChange={(e) =>
          setSelected(
            e.target.checked
              ? [...available, id]
              : available.filter((x) => x !== id),
          )
        }
      />
    ),
    toolbar: (
      <div className="delete-tools">
        <label className="checkbox">
          <input
            type="checkbox"
            disabled={busy || !items.length}
            checked={items.length > 0 && available.length === items.length}
            onChange={(e) =>
              setSelected(e.target.checked ? items.map((x) => x.id) : [])
            }
          />
          全选本页可删除项
        </label>
        <button
          className="danger"
          disabled={busy || !available.length}
          onClick={() => remove(available)}
        >
          {busy
            ? "正在删除…"
            : `删除所选${available.length ? `（${available.length}）` : ""}`}
        </button>
        {message && <p role="status">{message}</p>}
      </div>
    ),
  };
}
