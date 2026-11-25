// The kit's POPULAR badge, used only for the price change since the first price (rule 5).
// As a ribbon it hangs 8 px past the card's left edge, with the darker fold below.
import { formatChange } from "@/lib/format";
import { cn } from "@/lib/utils";
import Icon from "./Icon";

type Props = {
  changePct: number;
  ribbon?: boolean;
  className?: string;
};

export default function PriceChangeBadge({ changePct, ribbon = false, className }: Props) {
  return (
    <span
      className={cn(
        "relative inline-flex h-(--size-chip) items-center gap-1 rounded-sm bg-change-bg px-3 text-caption font-bold whitespace-nowrap text-change-text uppercase",
        ribbon && "rounded-bl-none",
        className,
      )}
    >
      <Icon name="chart-outline" size={14} />
      {formatChange(changePct)}
      {ribbon && (
        <span
          aria-hidden="true"
          className="absolute top-full left-0 border-t-8 border-l-8 border-t-change-fold border-l-transparent"
        />
      )}
    </span>
  );
}
