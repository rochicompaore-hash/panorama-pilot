import React from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

export const AuthTabs = ({ active }) => (
  <div className="mb-6 grid grid-cols-2 border border-border rounded-sm overflow-hidden" data-testid="auth-tabs">
    {[["login", "Accedi", "/login"], ["register", "Registrati", "/register"]].map(([key, label, to]) => (
      <Link key={key} to={to} data-testid={`auth-tab-${key}`}
        className={cn("py-2.5 text-center text-sm font-semibold uppercase tracking-wide transition-colors",
          active === key ? "bg-foreground text-background" : "bg-background text-muted-foreground hover:bg-secondary")}>
        {label}
      </Link>
    ))}
  </div>
);
