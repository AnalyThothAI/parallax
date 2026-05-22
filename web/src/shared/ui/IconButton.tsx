import clsx from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import "./IconButton.css";

type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> & {
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
    <button className={clsx("icon-button", className)} type={type} {...props}>
      {children}
    </button>
  );
}
