import { create } from "zustand";

import type { LiveMobileTask } from "../model/liveMobileTask";

type LiveTaskState = {
  mobileTask: LiveMobileTask;
  setMobileTask: (task: LiveMobileTask) => void;
};

export const useLiveTaskStore = create<LiveTaskState>((set) => ({
  mobileTask: "radar",
  setMobileTask: (mobileTask) => set({ mobileTask }),
}));
