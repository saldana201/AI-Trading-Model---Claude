/**
 * Server-side segment config for /admin: Refine's router integration reads
 * search params at runtime, so this segment must not be statically
 * prerendered. The client-side Refine mount lives in refine-shell.jsx.
 */
import { Suspense } from "react";
import RefineShell from "./refine-shell";

export const dynamic = "force-dynamic";

export default function AdminLayout({ children }) {
  return (
    <Suspense>
      <RefineShell>{children}</RefineShell>
    </Suspense>
  );
}
