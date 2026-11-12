import { AlertQueueView } from "@/components/views/alert-queue";

// Rendered client-side behind the auth gate; see (console)/layout.tsx
export const instant = false;

export default function Page() {
  return <AlertQueueView />;
}
