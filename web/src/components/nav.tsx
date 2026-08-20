"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AccountMenu } from "@/components/account-menu";

/** Nav targets, in the order the work flows: look, drill in, then feed it. */
export const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/spending", label: "Spending" },
  { href: "/accounts", label: "Accounts" },
  { href: "/transactions", label: "Transactions" },
  { href: "/import", label: "Import" },
  { href: "/rules", label: "Rules" },
] as const;

/**
 * `/accounts/7` lights up "Accounts". Exported so the test asserts the rule itself
 * rather than one rendering of it.
 */
export function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Nav() {
  const pathname = usePathname() ?? "/";

  return (
    <nav aria-label="Main" className="border-hairline bg-surface-1 border-b">
      <div className="mx-auto flex w-full max-w-5xl items-center gap-1 px-4">
        <span className="text-ink-secondary mr-3 py-3 text-sm font-medium whitespace-nowrap">
          Personal finance
        </span>
        {NAV_ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`border-b-2 px-3 py-3 text-sm whitespace-nowrap transition-colors ${
                active
                  ? "border-accent text-ink font-medium"
                  : "text-ink-secondary hover:text-ink border-transparent"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
        {/* Pushed to the right, and outside the scrolling group: an account control
            that scrolls off on a narrow screen is one nobody finds. */}
        <div className="ml-auto pl-3">
          <AccountMenu />
        </div>
      </div>
    </nav>
  );
}
