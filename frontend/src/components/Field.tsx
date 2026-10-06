import type { InputHTMLAttributes, SelectHTMLAttributes } from "react";

export const controlClass =
  "mt-1.5 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-500 focus:border-emerald-500/70 focus:ring-2 focus:ring-emerald-500/20";

type Props = InputHTMLAttributes<HTMLInputElement> & { label: string };

export function Field({ label, id, className, ...props }: Props) {
  return (
    <label className="block text-sm text-zinc-300" htmlFor={id}>
      {label}
      <input
        id={id}
        {...props}
        autoComplete="new-password"
        data-1p-ignore
        data-lpignore="true"
        className={`${controlClass} ${className ?? ""}`}
      />
    </label>
  );
}

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & { label: string };

export function SelectField({ label, id, className, children, ...props }: SelectProps) {
  return (
    <label className="block text-sm text-zinc-300" htmlFor={id}>
      {label}
      <select
        id={id}
        {...props}
        autoComplete="new-password"
        data-1p-ignore
        data-lpignore="true"
        className={`${controlClass} ${className ?? ""}`}
      >
        {children}
      </select>
    </label>
  );
}

