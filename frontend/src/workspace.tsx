import { createContext, useContext } from "react";
import type {
  Taxonomy,
  System,
  Dashboard as DashboardData,
  Job,
} from "./types";
type ContextValue = {
  isDemo: boolean;
  taxonomy: Taxonomy;
  system: System | null;
  dashboard: DashboardData | null;
  refresh: () => Promise<void>;
  startJob: (job: Job) => void;
  lastJob: string;
  newTicket: () => void;
};
export const WorkspaceContext = createContext<ContextValue>(null!);
export const useWorkspace = () => useContext(WorkspaceContext);
