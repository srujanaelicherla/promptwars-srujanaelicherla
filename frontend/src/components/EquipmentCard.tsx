import { Link } from "react-router";
import type { Equipment } from "../utilities/api";
import { buttonClassName, cardClassName } from "../utilities/classes";
import { departmentName } from "../utilities/demoCatalog";
import { resourceKind, resourceKindLabel } from "../utilities/resourceKind";
import { CategoryMark } from "./CategoryMark";

type EquipmentCardProps = {
  equipment: Equipment;
};

export function EquipmentCard({ equipment }: EquipmentCardProps) {
  const kind = resourceKind(equipment);
  return (
    <article className={cardClassName}>
      <div className="flex gap-4">
        <CategoryMark category={kind} />
        <div className="min-w-0">
          <h2 className="font-display text-xl text-ink">{equipment.name}</h2>
          <p className="mt-1 text-sm text-muted">
            {resourceKindLabel(kind)} · {departmentName(equipment.department_id)}
          </p>
          <p className="mt-2 text-sm capitalize text-accent">Catalog status: {equipment.status}</p>
        </div>
      </div>
      <p className="mt-4 text-sm leading-6 text-muted">{equipment.description}</p>
      <Link className={`${buttonClassName} mt-5`} to={`/equipment/${equipment.id}`}>
        {equipment.status === "available" ? "Book this" : "View details"}
      </Link>
    </article>
  );
}
