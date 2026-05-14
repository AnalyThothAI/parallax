import { Activity, FlaskConical, ListChecks } from "lucide-react";

import type { MobileTask } from "../model/mobileTask";

type MobileTaskNavProps = {
  activeTask: MobileTask;
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
];

export function MobileTaskNav({ activeTask, onTaskChange }: MobileTaskNavProps) {
  return (
    <nav aria-label="mobile cockpit tasks" className="mobile-task-nav">
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
