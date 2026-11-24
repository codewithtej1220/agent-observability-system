import {
  Activity, BellRing, Bot, BrainCircuit, ClipboardCheck, FileCheck2, GaugeCircle, Info, LayoutDashboard,
  CreditCard, Database, ListTree, MessagesSquare, PlugZap, ScrollText, Settings, ShieldCheck, Sparkles, Waves,
} from "lucide-react";

// Single source of truth for navigation: sidebar, breadcrumbs and the command palette.
export const NAV = [
  {
    group: "LLM monitoring",
    items: [
      { to: "/", label: "Overview", icon: LayoutDashboard, end: true, keywords: "dashboard home adherence" },
      { to: "/llm/calls", label: "Live calls", icon: Activity, keywords: "log requests prompts responses" },
      { to: "/llm/sessions", label: "Sessions", icon: MessagesSquare, keywords: "conversations threads users chat history" },
      { to: "/llm/contracts", label: "Prompt contracts", icon: FileCheck2, keywords: "rules policy enforce block repair" },
      { to: "/llm/alerts", label: "Alerts", icon: BellRing, badge: "alerts", keywords: "notifications slack" },
      { to: "/llm/prompts", label: "Prompts", icon: ScrollText, keywords: "prompt management versions labels production" },
      { to: "/llm/datasets", label: "Datasets & experiments", icon: Database, keywords: "evals test cases benchmark compare" },
      { to: "/llm/drift", label: "Drift tests", icon: Waves, keywords: "baseline schedule" },
      { to: "/llm/connect", label: "Connect LLMs", icon: PlugZap, keywords: "setup gateway sdk extension gemini chatgpt claude" },
    ],
  },
  {
    group: "Agent monitoring",
    items: [
      { to: "/agent-overview", label: "Agent overview", icon: GaugeCircle },
      { to: "/runs", label: "Runs", icon: ListTree, keywords: "traces" },
      { to: "/agents", label: "Agents", icon: Bot, keywords: "compare tool graph" },
      { to: "/review", label: "Review queue", icon: ClipboardCheck, badge: "review", keywords: "label feedback" },
      { to: "/models", label: "Detection models", icon: BrainCircuit, keywords: "ml metrics" },
      { to: "/policy", label: "Intervention policy", icon: Sparkles, keywords: "bandit rl" },
    ],
  },
  {
    group: "Workspace",
    items: [
      { to: "/settings", label: "Settings", icon: Settings, keywords: "keys members privacy judge" },
      { to: "/settings?tab=billing", label: "Plan & billing", icon: CreditCard, keywords: "subscription upgrade usage quota pricing trial" },
      { to: "/settings?tab=about", label: "About & how tracking works", icon: Info, keywords: "about project pipeline how it works" },
    ],
  },
];

export const ADMIN_NAV = {
  group: "Platform",
  items: [{ to: "/admin", label: "Platform admin", icon: ShieldCheck, keywords: "admin workspaces subscriptions customers" }],
};

export const ALL_NAV = NAV.flatMap((g) => g.items.map((i) => ({ ...i, group: g.group })));

/** Page title for the breadcrumb, from the current path. */
export function titleFor(pathname, search) {
  const tab = pathname === "/settings" && new URLSearchParams(search).get("tab");
  if (tab === "about") return ["Workspace", "About"];
  if (tab === "billing") return ["Workspace", "Plan & billing"];
  if (pathname === "/admin") return ["Platform", "Admin"];
  const exact = ALL_NAV.find((n) => n.to === pathname);
  if (exact) return [exact.group, exact.label];
  const parent = ALL_NAV.filter((n) => n.to !== "/" && pathname.startsWith(n.to + "/")).sort((a, b) => b.to.length - a.to.length)[0];
  if (parent) return [parent.group, parent.label, "Detail"];
  if (pathname.startsWith("/compare")) return ["Agent monitoring", "Agents", "Compare"];
  return [""];
}
