import { Component, type ErrorInfo, type ReactNode } from "react";

type ErrorBoundaryProps = {
  children: ReactNode;
  fallback?: ReactNode;
};

type ErrorBoundaryState = {
  error: Error | null;
};

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Route boundary caught an error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return this.props.fallback ?? <RouteErrorFallback error={this.state.error} />;
    }
    return this.props.children;
  }
}

function RouteErrorFallback({ error }: { error: Error }) {
  return (
    <section className="route-error-state" role="alert">
      <h2>Something broke</h2>
      <p>{error.message}</p>
    </section>
  );
}
