// The default project image: our own drawing, decorative (alt=""), until there are photos.
import placeholder from "@/assets/project-placeholder.svg?url";
import { cn } from "@/lib/utils";

type Props = {
  className?: string;
  /** The first image on screen loads eagerly, the rest lazily. */
  priority?: boolean;
};

export default function ProjectImage({ className, priority = false }: Props) {
  return (
    <img
      src={placeholder}
      alt=""
      width="704"
      height="400"
      loading={priority ? "eager" : "lazy"}
      decoding="async"
      fetchPriority={priority ? "high" : "auto"}
      className={cn("block w-full bg-bg-selected object-cover", className)}
    />
  );
}
