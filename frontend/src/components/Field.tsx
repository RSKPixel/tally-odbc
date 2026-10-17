import { useState, type InputHTMLAttributes, type SelectHTMLAttributes } from "react";

export const controlClass =
  "mt-1.5 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-500 focus:border-emerald-500/70 focus:ring-2 focus:ring-emerald-500/20";

type Props = InputHTMLAttributes<HTMLInputElement> & { label: string };

export function Field({ label, id, className, type, onFocus, ...props }: Props) {
  const isPassword = type === "password";
  const [blockAutofill, setBlockAutofill] = useState(isPassword);

  return (
    <label className="block text-sm text-zinc-300" htmlFor={id}>
      {label}
      <input
        id={id}
        type={type}
        {...props}
        // new-password blocks saved-login fill but makes Chrome offer "Suggest password".
        // one-time-code + readonly-until-focus keeps both suggestions and autofill off.
        autoComplete={isPassword ? "one-time-code" : "new-password"}
        data-1p-ignore
        data-lpignore="true"
        data-bwignore="true"
        data-form-type="other"
        readOnly={isPassword ? blockAutofill : props.readOnly}
        onFocus={(event) => {
          if (isPassword) setBlockAutofill(false);
          onFocus?.(event);
        }}
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
