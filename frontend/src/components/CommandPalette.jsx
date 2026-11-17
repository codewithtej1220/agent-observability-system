import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Command } from "cmdk";
import * as Dialog from "@radix-ui/react-dialog";
import { ArrowRight, LogOut, Monitor, Moon, Search, Sun } from "lucide-react";
import { setThemeMode } from "../theme";
import { ADMIN_NAV, NAV } from "../nav";
import { useAuth } from "../auth";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Ctrl/⌘+K: jump to any page, open a call or run by id, search calls, switch theme. */
export default function CommandPalette({ open, onOpenChange, onSignOut }) {
  const nav = useNavigate();
  const { me } = useAuth();
  const [query, setQuery] = useState("");

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  useEffect(() => { if (!open) setQuery(""); }, [open]);

  const go = (to) => { onOpenChange(false); nav(to); };
  const q = query.trim();

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="cmdk-overlay" />
        <Dialog.Content className="cmdk" aria-describedby={undefined}>
          <Dialog.Title className="sr-only">Command palette</Dialog.Title>
          <Command label="Command palette" loop>
            <Command.Input value={query} onValueChange={setQuery} placeholder="Go to a page, paste a call ID, or search calls…" autoFocus />
            <Command.List>
              <Command.Empty>No matches.</Command.Empty>
              {q && (
                <Command.Group heading="Search">
                  {UUID.test(q) && (
                    <>
                      <Command.Item value={`open-call-${q}`} onSelect={() => go(`/llm/calls/${q}`)}>
                        <ArrowRight size={16} /> Open LLM call <span className="mono">{q.slice(0, 8)}…</span>
                      </Command.Item>
                      <Command.Item value={`open-run-${q}`} onSelect={() => go(`/runs/${q}`)}>
                        <ArrowRight size={16} /> Open agent run <span className="mono">{q.slice(0, 8)}…</span>
                      </Command.Item>
                    </>
                  )}
                  <Command.Item value={`search-calls-${q}`} onSelect={() => go(`/llm/calls?q=${encodeURIComponent(q)}`)}>
                    <Search size={16} /> Search LLM calls for “{q}”
                  </Command.Item>
                  <Command.Item value={`search-runs-${q}`} onSelect={() => go(`/runs?q=${encodeURIComponent(q)}`)}>
                    <Search size={16} /> Search agent runs for “{q}”
                  </Command.Item>
                </Command.Group>
              )}
              {(me?.is_platform_admin ? [...NAV, ADMIN_NAV] : NAV).map((g) => (
                <Command.Group key={g.group} heading={g.group}>
                  {g.items.map((n) => (
                    <Command.Item key={n.to} value={`${g.group} ${n.label} ${n.keywords || ""}`} onSelect={() => go(n.to)}>
                      <n.icon size={16} /> {n.label}
                    </Command.Item>
                  ))}
                </Command.Group>
              ))}
              <Command.Group heading="Preferences">
                <Command.Item value="theme light" onSelect={() => { setThemeMode("light"); onOpenChange(false); }}><Sun size={16} /> Light theme</Command.Item>
                <Command.Item value="theme dark" onSelect={() => { setThemeMode("dark"); onOpenChange(false); }}><Moon size={16} /> Dark theme</Command.Item>
                <Command.Item value="theme system" onSelect={() => { setThemeMode("system"); onOpenChange(false); }}><Monitor size={16} /> System theme</Command.Item>
                <Command.Item value="sign out log out" onSelect={() => { onOpenChange(false); onSignOut(); }}><LogOut size={16} /> Sign out</Command.Item>
              </Command.Group>
            </Command.List>
            <div className="cmdk-foot"><span><kbd>↑</kbd> <kbd>↓</kbd> move</span><span><kbd>Enter</kbd> open</span><span><kbd>Esc</kbd> close</span></div>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
