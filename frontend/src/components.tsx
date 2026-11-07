import { ReactNode } from "react";
export function Heading({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">YOUR CREATIVE WORKSPACE</p>
        <h1>{title}</h1>
        <p className="muted">{subtitle}</p>
      </div>
      <div className="actions">{children}</div>
    </div>
  );
}
export function ErrorBox({ error }: { error?: string }) {
  return error ? (
    <p className="error" role="alert">
      {error}
    </p>
  ) : null;
}
export function Empty({
  text,
  children,
}: {
  text: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <div>◈</div>
      <h3>{text}</h3>
      <p>从一个小小的想法开始，让故事慢慢成形。</p>
      {children}
    </div>
  );
}
export function Pager({
  page,
  total,
  onChange,
}: {
  page: number;
  total: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="pager">
      <span>共 {total} 项</span>
      <div>
        <button disabled={page === 1} onClick={() => onChange(page - 1)}>
          上一页
        </button>
        <span>
          {page} / {Math.max(1, Math.ceil(total / 20))}
        </span>
        <button
          disabled={page * 20 >= total}
          onClick={() => onChange(page + 1)}
        >
          下一页
        </button>
      </div>
    </div>
  );
}
