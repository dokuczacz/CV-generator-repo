import * as React from 'react';

import { cn } from '@/lib/utils';

export interface ModalProps {
  open: boolean;
  title?: string;
  description?: string;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
}

export function Modal({ open, title, description, onClose, children, className }: ModalProps) {
  React.useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      <button
        aria-label="Close modal"
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        type="button"
      />
      <div className="absolute inset-0 flex items-center justify-center p-4">
        <div
          role="dialog"
          aria-modal="true"
          className={cn(
            'w-full max-w-5xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl',
            className
          )}
        >
          {(title || description) ? (
            <div className="border-b border-slate-100 p-4">
              {title ? <div className="text-sm font-semibold text-slate-900">{title}</div> : null}
              {description ? <div className="mt-1 text-sm text-slate-600">{description}</div> : null}
            </div>
          ) : null}
          <div className="p-4">{children}</div>
        </div>
      </div>
    </div>
  );
}

