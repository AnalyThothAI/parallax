import { UserRound } from "lucide-react";
import { useId } from "react";

import "./HandleFilter.css";

type HandleFilterProps = {
  ariaLabel: string;
  value: string;
  onChange: (handles: string) => void;
  placeholder?: string;
  id?: string;
};

export function HandleFilter({
  ariaLabel,
  id,
  onChange,
  placeholder = "handles",
  value,
}: HandleFilterProps) {
  const fallbackId = useId();
  const inputId = id ?? fallbackId;
  return (
    <label className="handle-filter" htmlFor={inputId}>
      <UserRound aria-hidden />
      <input
        aria-label={ariaLabel}
        id={inputId}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
