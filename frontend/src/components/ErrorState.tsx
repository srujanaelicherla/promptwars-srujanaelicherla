import type { ReactNode } from "react";

type ErrorStateProps = {
  title: string;
  message: string;
  children?: ReactNode;
};

export function ErrorState({ title, message, children }: ErrorStateProps) {
  return (
    <div role="alert" className="max-w-xl">
      <h2 className="font-display text-3xl leading-tight text-primary">{title}</h2>
      <p className="mt-4 text-base leading-7 text-ink">{message}</p>
      {children ? <div className="mt-6">{children}</div> : null}
    </div>
  );
}
