// One og:image per project, generated at build time: /og/{slug}.png.
import type { APIRoute, GetStaticPaths } from "astro";
import { loadCatalog } from "@/lib/catalog";
import { renderOgImage } from "@/lib/og";
import type { ProjectView } from "@/lib/projects";

export const getStaticPaths = (async () => {
  const projects = await loadCatalog();
  return projects.map((project) => ({ params: { slug: project.slug }, props: { project } }));
}) satisfies GetStaticPaths;

export const GET: APIRoute<{ project: ProjectView }> = async ({ props }) => {
  const png = await renderOgImage(props.project);
  return new Response(png, { headers: { "Content-Type": "image/png" } });
};
