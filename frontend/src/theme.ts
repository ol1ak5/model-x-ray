export const THEME = (import.meta.env.VITE_THEME as string | undefined) ?? "classic";
export const VARIANT = (import.meta.env.VITE_VARIANT as string | undefined) ?? "light";
export const GLOW = THEME === "glow";
