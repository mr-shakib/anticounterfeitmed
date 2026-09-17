"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { SessionProvider, useSession } from "@/components/Session";

function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href || (href !== "/" && pathname.startsWith(href));
  return (
    <Link href={href} className={active ? "active" : ""}>
      {label}
    </Link>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const { membership, loading, signOut } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !membership) router.replace("/login");
  }, [loading, membership, router]);

  if (loading) return <main className="center"><p className="muted">Loading…</p></main>;
  if (!membership) return null;

  const isAdmin = membership.role === "PLATFORM_ADMIN";
  const canRelease = membership.role === "RELEASE_MANAGER";

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <strong>MedSecure PQC</strong>
          <span className="muted">{membership.organization.name}</span>
        </div>
        <nav className="nav">
          <NavLink href="/" label="Overview" />

          {!isAdmin && (
            <>
              <div className="nav-heading">Manufacturer</div>
              <NavLink href="/products" label="Products" />
              <NavLink href="/batches" label="Batches" />
            </>
          )}

          {isAdmin && (
            <>
              <div className="nav-heading">Platform</div>
              <NavLink href="/organizations" label="Organizations" />
              <NavLink href="/reports" label="Investigations" />
              <NavLink href="/audit" label="Audit trail" />
            </>
          )}
        </nav>
        <div style={{ padding: "1rem 1.25rem" }}>
          <p className="muted" style={{ marginTop: 0 }}>
            {membership.username}
            <br />
            <span className="badge">{membership.role.replace(/_/g, " ").toLowerCase()}</span>
          </p>
          {canRelease && (
            <p className="muted">
              You can release units into circulation.
            </p>
          )}
          <button className="secondary" onClick={() => void signOut()}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="content">
        {membership.organization.is_suspended && (
          <div className="alert error">
            This organization is suspended. Issuance and activation are blocked.
          </div>
        )}
        {children}
      </main>
    </div>
  );
}

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <Shell>{children}</Shell>
    </SessionProvider>
  );
}
