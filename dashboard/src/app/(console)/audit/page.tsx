import { AuditView } from "@/components/views/audit";

// Rendered client-side behind the auth gate; see (console)/layout.tsx
export const instant = false;

export default function Page() {
  return <AuditView />;
}
