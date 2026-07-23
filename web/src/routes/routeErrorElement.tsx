import * as PageState from "@shared/ui/PageState";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";

export function RouteErrorElement() {
  const error = useRouteError();

  return <PageState.Error error={routeErrorMessage(error)} />;
}

export function RouteNotFoundElement() {
  return <PageState.Error error={new Error("404 Not Found")} />;
}

function routeErrorMessage(error: unknown): string {
  if (isRouteErrorResponse(error)) {
    return `${error.status} ${error.statusText}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  return "Route unavailable";
}
