import { OverviewView } from "@/components/views/overview";

// Rendered client-side behind the auth gate; see (console)/layout.tsx
export const instant = false;

export default function Page() {
  return <OverviewView />;
}
