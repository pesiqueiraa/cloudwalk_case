import * as Menu from "@radix-ui/react-dropdown-menu";
import { Check, ChevronDown, UserRound } from "lucide-react";
import { useApp } from "../hooks.js";

export function initials(name) {
  return name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
}

// Sem login: quem usa a tela diz quem é, e a fila se ajusta à equipe dessa pessoa
export default function AnalystMenu() {
  const { analyst, teamName, teamsWithAnalysts, chooseAnalyst } = useApp();
  return (
    <Menu.Root>
      <Menu.Trigger asChild>
        <button type="button" className="me-trigger" aria-label="Trocar de analista">
          <span className={analyst ? "avatar" : "avatar avatar-empty"} aria-hidden="true">
            {analyst ? initials(analyst.name) : <UserRound size={15} />}
          </span>
          <span className="me-text hide-sm">
            <strong>{analyst ? analyst.name : "Quem é você?"}</strong>
            {analyst && <small>{teamName[analyst.team_id] ?? analyst.team_id}</small>}
          </span>
          <ChevronDown size={14} aria-hidden="true" />
        </button>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content className="menu" align="end" sideOffset={6}>
          {teamsWithAnalysts.map((t) => (
            <Menu.Group key={t.id}>
              <Menu.Label className="menu-label">{t.name}</Menu.Label>
              {t.analysts.map((a) => (
                <Menu.Item key={a.id} className="menu-item" onSelect={() => chooseAnalyst(a.id)}>
                  {a.name}
                  {analyst?.id === a.id && <Check size={14} aria-label="atual" />}
                </Menu.Item>
              ))}
            </Menu.Group>
          ))}
          {analyst && (
            <>
              <Menu.Separator className="menu-sep" />
              <Menu.Item className="menu-item menu-muted" onSelect={() => chooseAnalyst("")}>Sair da fila</Menu.Item>
            </>
          )}
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}
