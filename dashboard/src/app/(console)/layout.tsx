import { ConsoleShell } from "@/components/shell";

// The console is gated client-side on a token in localStorage, so there is no
// meaningful server-rendered shell to validate for instant navigation.
export const instant = false;

export default function ConsoleLayout({ children }: LayoutProps<"/">) {
  return <ConsoleShell>{children}</ConsoleShell>;
}
