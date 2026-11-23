type CategoryMarkProps = {
  category: string;
};

export function CategoryMark({ category }: CategoryMarkProps) {
  return (
    <span
      className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-aqua text-sm font-medium text-primary"
      aria-hidden="true"
    >
      {category.slice(0, 2).toUpperCase()}
    </span>
  );
}
