"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ComponentType, type SVGProps } from "react";
import { Footer } from "@/components/Footer";
import {
  BuildingIcon,
  HistoryIcon,
  LayersIcon,
  LogOutIcon,
  OverviewIcon,
  PackageIcon,
  SearchAlertIcon,
  SettingsIcon,
  UsersIcon,
} from "@/components/Icons";
import { SessionProvider, useSession } from "@/components/Session";

function NavLink({
  href,
  label,
  icon: IconComponent,
}: {
  href: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}) {
  const pathname = usePathname();
  const active = pathname === href || (href !== "/" && pathname.startsWith(href));
  return (
    <Link href={href} className={active ? "active" : ""}>
      <IconComponent />
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
          <Image src="/mark.png" alt="" width={40} height={40} priority />
          <div className="brand-text">
            <strong>Anticounterfeit Med</strong>
            <span className="muted">{membership.organization.name}</span>
          </div>
        </div>
        <nav className="nav">
          <NavLink href="/" label="Overview" icon={OverviewIcon} />

          {!isAdmin && (
            <>
              <div className="nav-heading">Manufacturer</div>
              <NavLink href="/products" label="Products" icon={PackageIcon} />
              <NavLink href="/batches" label="Batches" icon={LayersIcon} />
            </>
          )}

          {isAdmin && (
            <>
              <div className="nav-heading">Platform</div>
              <NavLink href="/organizations" label="Organizations" icon={BuildingIcon} />
              <NavLink href="/staff" label="Staff access" icon={UsersIcon} />
              <NavLink href="/reports" label="Investigations" icon={SearchAlertIcon} />
              <NavLink href="/audit" label="Audit trail" icon={HistoryIcon} />
            </>
          )}

          <div className="nav-heading">Account</div>
          <NavLink href="/settings" label="Settings" icon={SettingsIcon} />
        </nav>
        <div className="account">
          <div className="account-row">
            <span className="avatar">{membership.username.slice(0, 2)}</span>
            <div className="account-who">
              <strong>{membership.username}</strong>
              <span>{membership.role.replace(/_/g, " ").toLowerCase()}</span>
            </div>
          </div>
          {canRelease && <p className="account-note">You can release units into circulation.</p>}
          <button className="secondary" onClick={() => void signOut()}>
            <LogOutIcon />
            Sign out
          </button>
        </div>
      </aside>
      <div className="main">
        <main className="content">
          {membership.organization.is_suspended && (
            <div className="alert error">
              This organization is suspended. Issuance and activation are blocked.
            </div>
          )}
          {children}
        </main>
        <Footer />
      </div>
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
