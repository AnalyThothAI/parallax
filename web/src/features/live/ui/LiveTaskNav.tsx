import { Activity, FlaskConical, ListChecks } from "lucide-react";

import type { LiveMobileTask } from "../model/liveMobileTask";

type LiveTaskNavProps = {
  activeTask: LiveMobileTask;
  onTaskChange: (task: LiveMobileTask) => void;
};

const TASKS: Array<{
  task: LiveMobileTask;
  label: string;
  icon: typeof ListChecks;
}> = [
  { task: "radar", label: "Radar", icon: ListChecks },
  { task: "tape", label: "Tape", icon: Activity },
  { task: "lab", label: "Lab", icon: FlaskConical },
];

export function LiveTaskNav({ activeTask, onTaskChange }: LiveTaskNavProps) {
  return (
    <nav aria-label="live mobile tasks" className="live-task-nav">
      {TASKS.map(({ icon: Icon, label, task }) => {
        return (
          <button
            aria-current={activeTask === task ? "page" : undefined}
            className={activeTask === task ? "active" : ""}
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
