/** Labels for seed IDs. Not a second catalog — IDs must match the backend seed. */

export const demoDepartments = [
  { id: "dept-physics", name: "Physics" },
  { id: "dept-chemistry", name: "Chemistry" },
  { id: "dept-biology", name: "Biology" },
  { id: "dept-engineering", name: "Engineering" },
] as const;

export const demoLabs = [
  { id: "lab-optics", name: "Optics laboratory" },
  { id: "lab-analytical", name: "Analytical laboratory" },
  { id: "lab-maker", name: "Electronics and fabrication laboratory" },
  { id: "lab-biology", name: "Cell and molecular laboratory" },
] as const;

export const demoCategories = [
  "lab-station",
  "kit",
  "optics",
  "spectroscopy",
  "chromatography",
  "safety",
  "measurement",
  "electronics",
  "fabrication",
  "workspace",
  "additive",
  "centrifugation",
  "cryogenics",
  "detection",
  "electrophoresis",
  "electrochemistry",
  "gc",
  "imaging",
  "incubation",
  "inspection",
  "joining",
  "laser",
  "magnetism",
  "mechanics",
  "mechanical",
  "metrology",
  "microscopy",
  "nmr",
  "pcr",
  "power",
  "purification",
  "rf",
  "robotics",
  "sample-prep",
  "sequencing",
  "synthesis",
  "thermal",
  "vacuum",
] as const;

export const demoProjects = [
  { id: "proj-raman", title: "Raman alignment exercise" },
  { id: "proj-hplc-method", title: "Caffeine method sketch" },
  { id: "proj-sensor", title: "Sensor board bring-up" },
  { id: "proj-amplicon", title: "Synthetic amplicon exercise" },
] as const;

export function departmentName(id: string): string {
  return demoDepartments.find((item) => item.id === id)?.name ?? id;
}

export function labName(id: string): string {
  return demoLabs.find((item) => item.id === id)?.name ?? id;
}

export function projectTitle(id: string): string {
  return demoProjects.find((item) => item.id === id)?.title ?? id;
}

const PROJECT_BY_DEPARTMENT: Record<string, string> = {
  "dept-physics": "proj-raman",
  "dept-chemistry": "proj-hplc-method",
  "dept-engineering": "proj-sensor",
  "dept-biology": "proj-amplicon",
};

export function defaultProjectId(departmentId: string): string {
  return PROJECT_BY_DEPARTMENT[departmentId] ?? demoProjects[0].id;
}
