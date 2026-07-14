import { create } from "zustand";

interface AppState {
  selectedDisease: string;
  selectedDrug: string | null;
  setSelectedDisease: (id: string) => void;
  setSelectedDrug: (id: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedDisease: "EFO_0000519",
  selectedDrug: null,
  setSelectedDisease: (id) => set({ selectedDisease: id }),
  setSelectedDrug: (id) => set({ selectedDrug: id }),
}));
