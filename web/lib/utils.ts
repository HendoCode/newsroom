import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge conditional class names and de-conflict Tailwind utilities. Standard shadcn/ui
 * helper used by every token-driven component.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
