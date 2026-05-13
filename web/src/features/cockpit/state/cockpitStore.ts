import { create } from "zustand";

import type { MobileTask } from "../model/mobileTask";

type CockpitState = {
  mobileTask: MobileTask;
  setMobileTask: (task: MobileTask) => void;
};

export const useCockpitStore = create<CockpitState>((set) => ({
  mobileTask: "radar",
  setMobileTask: (mobileTask) => set({ mobileTask }),
}));
