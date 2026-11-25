/** Labels of the search controls, apart from the controls so the first bundle stays small. */
import type { SortKey } from "@/lib/search";

/** Each order as its menu row says it. */
export const SORT_OPTION: Record<SortKey, string> = {
  precio: "Precio: menor a mayor",
  precio_desc: "Precio: mayor a menor",
  subida: "Mayor subida",
  nombre: "Nombre",
};

/** Each order as its trigger names it. */
export const SORT_SHORT: Record<SortKey, string> = {
  precio: "Menor precio",
  precio_desc: "Mayor precio",
  subida: "Mayor subida",
  nombre: "Nombre",
};
