/** Built-in analysis presets; ids match backend/src/services/presets.py. */
export type AnalysisPreset = { id: string; name: string; description: string; risk_tolerance: "low" | "medium" };
export const ANALYSIS_PRESETS: readonly AnalysisPreset[] = [
  { id: "brand_launch", name: "Brand launch", description: "Assess cultural fit and market opportunity for a new brand launch.", risk_tolerance: "low" },
  { id: "brand_repositioning", name: "Brand repositioning", description: "Evaluate audience overlap and transition paths for a repositioning.", risk_tolerance: "medium" },
  { id: "market_entry", name: "Market entry", description: "Compare cultural affinity and regional opportunity before entering a market.", risk_tolerance: "medium" },
];
export function getAnalysisPreset(id: string): AnalysisPreset | undefined {
  return ANALYSIS_PRESETS.find((preset) => preset.id === id);
}
