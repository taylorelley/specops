import { defineConfig } from "vitepress";

export default defineConfig({
  base: "/specops/",
  ignoreDeadLinks: true,
  appearance: false, // Light theme only, match specops-ui
  title: "SpecOps",
  description:
    "Deploy autonomous AI teams that run your work — 24/7, securely, at scale. Infrastructure for persistent, proactive agent workforces.",
  themeConfig: {
    logo: "/specops.svg",
    nav: [
      { text: "Home", link: "/" },
      { text: "Guide", link: "/guide/quickstart" },
      { text: "Reference", link: "/reference/terminology" },
    ],
    sidebar: {
      "/guide/": [
        {
          text: "Guide",
          items: [
            { text: "Quick Start", link: "/guide/quickstart" },
            { text: "Product Principles", link: "/guide/principles" },
            { text: "Configuration", link: "/guide/configuration" },
            { text: "Reverse Proxy", link: "/guide/reverse-proxy" },
            { text: "Channels", link: "/guide/channels" },
            { text: "Plans", link: "/guide/plans" },
            { text: "API Tools", link: "/guide/api-tools" },
            { text: "Guardrails", link: "/guide/guardrails" },
            { text: "Human-in-the-Loop", link: "/guide/hitl" },
            { text: "Security", link: "/guide/security" },
          ],
        },
      ],
      "/reference/": [
        {
          text: "Reference",
          items: [
            { text: "Terminology", link: "/reference/terminology" },
            { text: "Execution events", link: "/reference/execution-events" },
          ],
        },
      ],
    },
    socialLinks: [
      {
        icon: "github",
        link: "https://github.com/taylorelley/specops",
      },
    ],
  },
});
