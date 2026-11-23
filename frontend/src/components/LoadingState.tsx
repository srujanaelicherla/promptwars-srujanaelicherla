type LoadingStateProps = {
  label?: string;
};

export function LoadingState({ label = "Loading" }: LoadingStateProps) {
  return (
    <p role="status" aria-label={label} className="text-muted">
      {label}
    </p>
  );
}
