import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { EmptyState } from "../components/EmptyState";
import { EquipmentCard } from "../components/EquipmentCard";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AppShell } from "../layouts/AppShell";
import { ApiError, listEquipment, type Equipment, type EquipmentQuery, type ResourceKind } from "../utilities/api";
import { resourceKind } from "../utilities/resourceKind";
import { buttonClassName, cardClassName } from "../utilities/classes";
import { demoCategories, demoDepartments } from "../utilities/demoCatalog";
import { usePageTitle } from "../utilities/usePageTitle";

const fieldClassName = "min-h-11 rounded-xl border border-line bg-raised px-3 text-sm text-ink";

export function EquipmentPage() {
  usePageTitle("Book · LabLink");
  const [params, setParams] = useSearchParams();
  const search = params.get("search") ?? "";
  const department = params.get("department") ?? "";
  const category = params.get("category") ?? "";
  const status = params.get("status") ?? "";
  const kind = (params.get("kind") ?? "") as ResourceKind | "";
  const [draft, setDraft] = useState(search);
  const [items, setItems] = useState<Equipment[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(search);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    setItems(null);
    setError(null);
    const query: EquipmentQuery = {};
    if (search) query.search = search;
    if (department) query.department = department;
    if (category) query.category = category;
    if (status) query.status = status;
    listEquipment(query)
      .then((result) => {
        if (!cancelled) {
          setItems(result.items);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "Equipment could not be loaded.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [search, department, category, status, kind]);

  const visible =
    items === null ? null : kind ? items.filter((item) => resourceKind(item) === kind) : items;

  function update(next: Record<string, string>) {
    const merged = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value) {
        merged.set(key, value);
      } else {
        merged.delete(key);
      }
    }
    setParams(merged);
  }

  return (
    <AppShell title="Book a resource">
      <form
        className={`${cardClassName} grid gap-3 md:grid-cols-4`}
        onSubmit={(event) => {
          event.preventDefault();
          update({ search: draft.trim() });
        }}
      >
        <label className="block text-sm font-medium text-primary">
          Search
          <input
            className={`${fieldClassName} mt-1 w-full`}
            type="search"
            name="search"
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
            }}
          />
        </label>
        <label className="block text-sm font-medium text-primary">
          Department
          <select
            className={`${fieldClassName} mt-1 w-full`}
            value={department}
            onChange={(event) => {
              update({ department: event.target.value });
            }}
          >
            <option value="">All</option>
            {demoDepartments.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm font-medium text-primary">
          Type
          <select
            className={`${fieldClassName} mt-1 w-full`}
            value={kind}
            onChange={(event) => {
              update({ kind: event.target.value });
            }}
          >
            <option value="">All types</option>
            <option value="equipment">Equipment</option>
            <option value="lab-station">Lab stations</option>
            <option value="kit">Kits</option>
          </select>
        </label>
        <label className="block text-sm font-medium text-primary">
          Category
          <select
            className={`${fieldClassName} mt-1 w-full`}
            value={category}
            onChange={(event) => {
              update({ category: event.target.value });
            }}
          >
            <option value="">All</option>
            {demoCategories.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm font-medium text-primary">
          Status
          <select
            className={`${fieldClassName} mt-1 w-full`}
            value={status}
            onChange={(event) => {
              update({ status: event.target.value });
            }}
          >
            <option value="">All</option>
            <option value="available">available</option>
            <option value="maintenance">maintenance</option>
            <option value="retired">retired</option>
          </select>
        </label>
        <button className={`${buttonClassName} md:col-span-4 md:w-fit`} type="submit">
          Search catalog
        </button>
      </form>

      <div className="mt-6">
        {error ? (
          <ErrorState title="Equipment unavailable" message={error} />
        ) : visible === null ? (
          <LoadingState label="Loading equipment" />
        ) : visible.length === 0 ? (
          <EmptyState
            title="No matching items"
            description="Nothing in the catalog matches these filters."
          />
        ) : (
          <ul className="grid list-none gap-4 p-0 md:grid-cols-2">
            {visible.map((item) => (
              <li key={item.id}>
                <EquipmentCard equipment={item} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </AppShell>
  );
}
