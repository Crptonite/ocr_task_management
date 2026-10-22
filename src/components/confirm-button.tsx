"use client";

import type { ReactNode } from "react";

/** Submit button that asks for confirmation first; use inside a <form action={...}>. */
export function ConfirmButton({
  message,
  className = "btn-danger",
  children,
}: {
  message: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <button
      className={className}
      onClick={(e) => {
        if (!confirm(message)) e.preventDefault();
      }}
    >
      {children}
    </button>
  );
}
