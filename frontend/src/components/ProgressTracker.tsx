import { NODES, type NodeName } from "../types";

const LABELS: Record<NodeName, string> = {
  retrieve: "Retrieve context",
  sentiment: "Sentiment",
  extraction: "Extraction",
  risk: "Risk",
  summary: "Summary",
  persist: "Save",
};

export function ProgressTracker({ done }: { done: Set<string> }) {
  return (
    <ol className="progress">
      {NODES.map((node) => (
        <li key={node} className={done.has(node) ? "step done" : "step"}>
          <span className="dot" />
          {LABELS[node]}
        </li>
      ))}
    </ol>
  );
}
