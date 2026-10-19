import type { ReactNode } from "react";

import styles from "./Button.module.css";

export type Variant = "primary" | "secondary" | "ghost" | "danger";

type Props = {
  variant?: Variant;
  className?: string;
  children: ReactNode;
  href?: string;
  htmlFor?: string;
  type?: "button" | "submit";
  disabled?: boolean;
  onClick?: () => void;
};

export default function Button({ variant = "secondary", className, children, href, htmlFor, type = "button", disabled, onClick }: Props) {
  const classes = [styles[variant], className].filter(Boolean).join(" ");
  if (htmlFor) return <label className={classes} htmlFor={htmlFor}>{children}</label>;
  if (href) return <a className={classes} href={href}>{children}</a>;
  return (
    <button type={type} className={classes} disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
}
