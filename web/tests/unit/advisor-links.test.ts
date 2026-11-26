import { describe, expect, it } from "vitest";

import { allowedHostsFrom, linkPolicy } from "../../src/lib/advisor/links";

const hosts = allowedHostsFrom([
  "https://www.londonogomez.com/proyectos/arrayanes",
  "https://constructoracapital.com/medellin/vento",
  "http://insecure.example/x",
  "not a url",
]);
const policy = linkPolicy(hosts);

describe("allowedHostsFrom", () => {
  it("keeps the https hosts of the catalog, without www", () => {
    expect(hosts).toEqual(["constructoracapital.com", "londonogomez.com"]);
  });
});

describe("linkPolicy", () => {
  it("keeps project pages of the site, with their final slash", () => {
    expect(policy("/proyectos/arrayanes-del-sur/")).toEqual({
      href: "/proyectos/arrayanes-del-sur/",
      external: false,
    });
    expect(policy("/proyectos/arrayanes-del-sur")).toEqual({
      href: "/proyectos/arrayanes-del-sur/",
      external: false,
    });
  });

  it("keeps https pages of the catalog's developers, with or without www", () => {
    expect(policy("https://www.londonogomez.com/proyectos/arrayanes")).toEqual({
      href: "https://www.londonogomez.com/proyectos/arrayanes",
      external: true,
    });
    expect(policy("https://londonogomez.com/")?.external).toBe(true);
    expect(policy("https://CONSTRUCTORACAPITAL.com/vento")?.href).toBe(
      "https://constructoracapital.com/vento",
    );
  });

  it.each([
    "https://evil.example/proyectos/x",
    "https://londonogomez.com.evil.example/",
    "https://evil.example/?next=https://londonogomez.com",
    "http://londonogomez.com/",
    "https://user:pass@londonogomez.com/",
    "https://londonogomez.com:8443/",
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "mailto:ventas@londonogomez.com",
    "//evil.example/proyectos/x/",
    "/\\evil.example/proyectos/x/",
    "/proyectos/",
    "/proyectos/../terminos/",
    "/proyectos/Mayusculas/",
    "/terminos/",
    "proyectos/x/",
    "",
  ])("leaves %j as text", (href) => {
    expect(policy(href)).toBeNull();
  });
});
