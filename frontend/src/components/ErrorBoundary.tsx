import { Component, type ErrorInfo, type ReactNode } from "react";
import { ErrorState } from "./ErrorState";
import { textLinkClassName } from "../utilities/classes";

type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  hasError: boolean;
};

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("LabLink interface error", error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="min-h-screen bg-paper px-5 py-16 text-ink">
        <ErrorState
          title="This page could not be shown"
          message="The LabLink interface hit an unexpected error. No laboratory request was submitted."
        >
          <a className={textLinkClassName} href="/">
            Reload LabLink
          </a>
        </ErrorState>
      </div>
    );
  }
}
