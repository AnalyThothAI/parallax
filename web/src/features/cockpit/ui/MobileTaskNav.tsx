import { Activity, FlaskConical, ListChecks, PanelRight } from "lucide-react";

import type { MobileTask } from "../model/mobileTask";

type MobileTaskNavProps = {
  activeTask: MobileTask;
  detailAvailable: boolean;
  onTaskChange: (task: MobileTask) => void;
};

const TASKS: Array<{
  task: MobileTask;
  label: string;
  icon: typeof ListChecks;
}> = [
  { task: "radar", label: "Radar", icon: ListChecks },
  { task: "tape", label: "Tape", icon: Activity },
  { task: "lab", label: "Lab", icon: FlaskConical },
  { task: "detail", label: "Detail", icon: PanelRight },
];

export function MobileTaskNav({ activeTask, detailAvailable, onTaskChange }: MobileTaskNavProps) {
  return (
    <nav aria-label="mobile cockpit tasks" className="mobile-task-nav">
      {TASKS.map(({ icon: Icon, label, task }) => {
        const disabled = task === "detail" && !detailAvailable;
        return (
          <button
            aria-current={activeTask === task ? "page" : undefined}
            className={activeTask === task ? "active" : ""}
            disabled={disabled}
            key={task}
            type="button"
            onClick={() => onTaskChange(task)}
          >
            <Icon aria-hidden />
            <span>{label}</span>
          </button>
        );
      })}
    </nav>
  );
}
