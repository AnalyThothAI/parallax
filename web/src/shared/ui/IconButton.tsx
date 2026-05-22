import { cn } from "@lib/utils";
import type { ComponentProps, ReactNode } from "react";

import { Button } from "./button";

type IconButtonProps = Omit<
  ComponentProps<typeof Button>,
  "aria-label" | "asChild" | "size" | "variant"
> & {
  "aria-label": string;
  children: ReactNode;
};

export function IconButton({
  children,
  className = "",
  type = "button",
  ...props
}: IconButtonProps) {
  return (
    <Button
      className={cn("size-7 p-0", className)}
      size="icon-sm"
      type={type}
      variant="outline"
      {...props}
    >
      {children}
    </Button>
  );
}
