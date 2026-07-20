// Phase 9 — admin segment config.
//
// Refine's router reads search params at runtime, which Next 14 cannot
// statically prerender. Forcing dynamic rendering plus a Suspense boundary
// is why the admin pages don't throw `useSearchParams()` prerender errors.
// If you add a new page under /admin and hit that error, this file is why
// the existing ones work.

import { Suspense } from "react";
import RefineShell from "./refine-shell";

export const dynamic = "force-dynamic";

export default function AdminLayout({ children }) {
  return (
    <Suspense fallback={<div className="wrap" style={{ padding: 24 }}>Loading admin…</div>}>
      <RefineShell>{children}</RefineShell>
    </Suspense>
  );
}
