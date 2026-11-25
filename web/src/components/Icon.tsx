// An icon of the kit (or its fallback), inlined so it takes the text color. Astro pages render
// it without hydrating it, so it ships no JavaScript there; the search island bundles it.
import { type IconName, iconParts } from "@/lib/icons";

type Props = {
  name: IconName;
  size?: number;
  className?: string;
  /** Accessible name; leave it out for decorative icons next to text. */
  label?: string;
};

export default function Icon({ name, size, className, label }: Props) {
  const { attributes, inner } = iconParts(name, { size, className, label });
  // The markup comes from our own SVG files, read at build time, never from user input.
  return <svg {...attributes} dangerouslySetInnerHTML={{ __html: inner }} />;
}
