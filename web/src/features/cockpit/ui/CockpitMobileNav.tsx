import type { MobileTask } from "../model/mobileTask";

import { MobileTaskNav } from "./MobileTaskNav";

export type CockpitMobileNavProps = {
  mobileTask: MobileTask;
  onMobileTaskChange: (task: MobileTask) => void;
};

export function CockpitMobileNav({ mobileTask, onMobileTaskChange }: CockpitMobileNavProps) {
  return <MobileTaskNav activeTask={mobileTask} onTaskChange={onMobileTaskChange} />;
}
