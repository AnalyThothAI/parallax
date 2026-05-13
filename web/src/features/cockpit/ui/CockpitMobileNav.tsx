import type { MobileTask } from "../model/mobileTask";

import { MobileTaskNav } from "./MobileTaskNav";

export type CockpitMobileNavProps = {
  mobileTask: MobileTask;
  detailAvailable: boolean;
  onMobileTaskChange: (task: MobileTask) => void;
};

export function CockpitMobileNav({
  mobileTask,
  detailAvailable,
  onMobileTaskChange,
}: CockpitMobileNavProps) {
  return (
    <MobileTaskNav
      activeTask={mobileTask}
      detailAvailable={detailAvailable}
      onTaskChange={onMobileTaskChange}
    />
  );
}
