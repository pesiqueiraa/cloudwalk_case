import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

// Gaveta lateral (side) ou diálogo central (center). O Radix cuida de foco, Esc e leitor de tela.
export default function Sheet({ open, onOpenChange, title, description, side = "right", width, children, footer }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content className={`sheet sheet-${side}`} style={width ? { "--sheet-w": width } : undefined}>
          <div className="sheet-head">
            <div>
              <Dialog.Title className="sheet-title">{title}</Dialog.Title>
              {description
                ? <Dialog.Description className="sheet-desc">{description}</Dialog.Description>
                : <Dialog.Description className="sr-only">{title}</Dialog.Description>}
            </div>
            <Dialog.Close className="btn btn-icon" aria-label="Fechar"><X size={16} /></Dialog.Close>
          </div>
          <div className="sheet-body">{children}</div>
          {footer && <div className="sheet-foot">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
