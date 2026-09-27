type EmptyStateProps = {
  title: string;
  detail: string;
};

export function EmptyState({ title, detail }: EmptyStateProps) {
  return <div className="empty-state"><span className="empty-mark">⌁</span><strong>{title}</strong><p>{detail}</p></div>;
}
