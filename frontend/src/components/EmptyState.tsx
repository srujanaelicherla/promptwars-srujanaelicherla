type EmptyStateProps = {
  title: string;
  description: string;
};

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="rounded-2xl border border-dashed border-line bg-raised px-5 py-8">
      <h3 className="font-display text-xl text-primary">{title}</h3>
      <p className="mt-2 max-w-xl text-base leading-7 text-muted">{description}</p>
    </div>
  );
}
