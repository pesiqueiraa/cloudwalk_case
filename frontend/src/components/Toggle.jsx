import * as Switch from "@radix-ui/react-switch";

export default function Toggle({ checked, onChange, label }) {
  return (
    <span className="toggle">
      <Switch.Root className="switch" checked={checked} onCheckedChange={onChange} aria-label={label}>
        <Switch.Thumb className="switch-thumb" />
      </Switch.Root>
      <span className="toggle-text" aria-hidden="true">{checked ? "Ativa" : "Desativada"}</span>
    </span>
  );
}
