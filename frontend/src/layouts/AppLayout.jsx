import React, { useState, useEffect } from "react";
import { Outlet, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/api/client";
import {
  House, Users, ShieldCheck, Buildings, Hash, Files, ClockCounterClockwise,
  Bell, Devices, EnvelopeSimple, MagnifyingGlass, SignOut, List, X, CaretDown,
  UserCircle, IdentificationCard, ListChecks, CalendarBlank, Target, WhatsappLogo,
  Kanban, FileText, Play,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// P0 Operational — sidebar semplificata (Feb 2026)
// - Preventivatore unificato: Clienti → Preventivi → Catalogo prodotti → Servizi
// - Route legacy nascoste dalla sidebar (non eliminate): /pricelists, /pricelist-importer, /parametric, /parametric/admin
// - /product-simulator restricted a Admin/tech
// - /quote-structure viene esposto come "Catalogo prodotti" (schermata operativa)
const NAV = [
  {
    group: "core",
    label: "Operatività",
    items: [
      { to: "/dashboard", i18n: "nav.dashboard", icon: House, perm: "dashboard.view" },
      { to: "/customers", i18n: "nav.customers", icon: UserCircle, perm: "crm.customers.view" },
      { to: "/quotes", label: "Preventivi", icon: FileText, perm: "quotes.view" },
      { to: "/leads", i18n: "nav.leads", icon: Kanban, perm: "crm.leads.view" },
      { to: "/tasks", i18n: "nav.tasks", icon: ListChecks, perm: "crm.tasks.view" },
      { to: "/calendar", i18n: "nav.calendar", icon: CalendarBlank, perm: "crm.appointments.view" },
      { to: "/contracts", label: "Ordini e contratti", icon: FileText, perm: "contracts.view" },
    ],
  },
  {
    group: "products",
    label: "Prodotti",
    items: [
      { to: "/quote-structure", label: "Catalogo prodotti", icon: FileText, perm: "products.view" },
      { to: "/pricing-hub", label: "Servizi e prezzi semplici", icon: Hash, perm: "pricelists.view" },
    ],
  },
  {
    group: "operations",
    label: "Produzione e Posa",
    items: [
      { to: "/surveys", label: "Rilievi tecnici", icon: FileText, perm: "surveys.view" },
      { to: "/technical-schedules", label: "Abaci tecnici", icon: FileText, perm: "surveys.view" },
      { to: "/sales-orders", label: "Ordini cliente", icon: FileText, perm: "sales_orders.view" },
      { to: "/production-orders", label: "Produzione", icon: FileText, perm: "production.view" },
      { to: "/qc", label: "Qualità", icon: ShieldCheck, perm: "qc.view" },
      { to: "/installation-plans", label: "Pianificazione posa", icon: CalendarBlank, perm: "installation.view" },
      { to: "/service-tickets", label: "Assistenza", icon: ListChecks, perm: "service.view" },
      { to: "/suppliers", label: "Fornitori", icon: Buildings, perm: "suppliers.view" },
      { to: "/purchase-orders", label: "Ordini fornitore", icon: FileText, perm: "purchase_orders.view" },
      { to: "/items", label: "Magazzino", icon: Hash, perm: "items.view" },
    ],
  },
  {
    group: "crm_more",
    label: "CRM avanzato",
    items: [
      { to: "/contacts", i18n: "nav.contacts", icon: IdentificationCard, perm: "crm.contacts.view" },
      { to: "/goals", i18n: "nav.goals", icon: Target, perm: "crm.goals.view" },
      { to: "/attachments", i18n: "nav.attachments", icon: Files, perm: "attachments.view" },
      { to: "/templates", i18n: "nav.templates", icon: FileText, perm: "quotes.view" },
      { to: "/clauses", i18n: "nav.clauses", icon: FileText, perm: "quotes.view" },
    ],
  },
  {
    group: "finance",
    label: "Amministrazione e CFO",
    items: [
      { to: "/payment-plans", label: "Piani pagamenti", icon: Hash, perm: "admin.payments.view" },
      { to: "/cfo", label: "Dashboard CFO", icon: Target, perm: "treasury.view" },
      { to: "/ai-cfo", label: "AI CFO & BI", icon: Target, perm: "ai_cfo.view" },
      { to: "/legal-entities", label: "Società (Multi-company)", icon: Buildings, perm: "company.view" },
    ],
  },
  {
    group: "tech_config",
    label: "Configurazione tecnica",
    items: [
      // Ristretta ad admin — pricing_admin.manage (o superuser via has())
      { to: "/product-catalog", label: "Tipologie e configuratore", icon: FileText, perm: "products.manage" },
      { to: "/product-simulator", label: "Simulatore tecnico (debug)", icon: Play, perm: "pricing_admin.manage" },
      { to: "/geometry-builder", label: "Configuratore geometrico", icon: FileText, perm: "products.manage" },
      { to: "/site-conditions", label: "Questionario cantiere", icon: FileText, perm: "quotes.view" },
    ],
  },
  {
    group: "platform",
    label: "Platform Owner",
    items: [
      { to: "/saas-platform", label: "SaaS Modularization", icon: ShieldCheck, perm: null },
      { to: "/platform-site-config", label: "Configurazione landing", icon: Buildings, perm: null },
    ],
  },
  {
    group: "governance",
    label: "Utenti e permessi",
    items: [
      { to: "/users", i18n: "nav.users", icon: Users, perm: "users.view" },
      { to: "/roles", i18n: "nav.roles", icon: ShieldCheck, perm: "roles.view" },
      { to: "/company", i18n: "nav.company", icon: Buildings, perm: "company.view" },
      { to: "/sequences", i18n: "nav.sequences", icon: Hash, perm: "sequences.view" },
    ],
  },
  {
    group: "system",
    label: "Impostazioni sistema",
    items: [
      { to: "/notifications", i18n: "nav.notifications", icon: Bell, perm: null },
      { to: "/search", i18n: "nav.search", icon: MagnifyingGlass, perm: "search.global" },
      { to: "/audit", i18n: "nav.audit", icon: ClockCounterClockwise, perm: "audit.view" },
      { to: "/sessions", i18n: "nav.sessions", icon: Devices, perm: null },
      { to: "/email-settings", label: "Impostazioni email", icon: EnvelopeSimple, perm: "email.view_settings" },
      { to: "/email-logs", i18n: "nav.email_logs", icon: EnvelopeSimple, perm: "email.view_logs" },
      { to: "/whatsapp-logs", i18n: "nav.whatsapp_logs", icon: WhatsappLogo, perm: "audit.view" },
    ],
  },
];

// Route mantenute per compatibilità interna ma NASCOSTE dalla sidebar:
// - /pricelists         → gestione componenti spostata in Configurazione tecnica (backlog Fase 1)
// - /pricelist-importer → azione amministrativa interna
// - /parametric         → engine legacy, integrazione futura
// - /parametric/admin   → engine legacy, integrazione futura

export default function AppLayout() {
  const { t } = useTranslation();
  const { user, logout, has } = useAuth();
  const [openMobile, setOpenMobile] = useState(false);
  const [notif, setNotif] = useState({ unread: 0, items: [] });
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQ, setSearchQ] = useState("");
  const [searchRes, setSearchRes] = useState([]);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => setOpenMobile(false), [location.pathname]);

  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await api.get("/notifications", { params: { limit: 10 } });
        setNotif(data);
      } catch {}
    };
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [location.pathname]);

  useEffect(() => {
    if (!searchQ) { setSearchRes([]); return; }
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get("/search", { params: { q: searchQ } });
        setSearchRes(data.results);
      } catch {}
    }, 250);
    return () => clearTimeout(t);
  }, [searchQ]);

  const handleLogout = async () => {
    await logout();
    toast.success("Uscita effettuata");
    navigate("/login");
  };

  const initials = ((user?.first_name?.[0] || "") + (user?.last_name?.[0] || "")).toUpperCase()
    || (user?.email?.[0] || "?").toUpperCase();

  const NavGroup = ({ group }) => (
    <div className="mt-6 first:mt-2">
      <div className="overline px-3 mb-2 text-muted-foreground">{group.label || t(`nav.${group.group}`)}</div>
      <div className="flex flex-col">
        {group.items.map((it) => {
          if (it.perm && !has(it.perm)) return null;
          const Icon = it.icon;
          return (
            <NavLink
              key={it.to}
              to={it.to}
              data-testid={`nav-${it.to.replace(/\//g, "")}`}
              className={({ isActive }) =>
                cn(
                  "group flex items-center gap-3 px-3 py-2 text-sm font-medium",
                  "border-l-2 border-transparent",
                  "hover:bg-secondary hover:border-[hsl(var(--brand-red))]",
                  isActive && "bg-secondary border-[hsl(var(--brand-red))] text-foreground"
                )
              }
            >
              <Icon size={18} weight="duotone" aria-hidden />
              <span>{it.label || t(it.i18n)}</span>
            </NavLink>
          );
        })}
      </div>
    </div>
  );

  const Sidebar = (
    <aside className="h-full w-[280px] bg-card border-r border-border flex flex-col">
      <div className="p-6 border-b border-border">
        <div className="overline">Infissi Express</div>
        <div className="font-display text-lg font-black tracking-tight mt-1">CLOUD ERP</div>
        <div className="mt-2 text-[10px] font-mono-plex text-muted-foreground">
          M2 · CRM
        </div>
      </div>
      <div className="flex-1 overflow-y-auto pb-4">
        {NAV.map((g) => (
          <NavGroup key={g.group} group={g} />
        ))}
      </div>
      <div className="p-4 border-t border-border text-[10px] font-mono-plex text-muted-foreground">
        EUR · Europe/Rome
      </div>
    </aside>
  );

  return (
    <div className="min-h-screen flex bg-background">
      {/* Desktop sidebar */}
      <div className="hidden lg:block">{Sidebar}</div>

      {/* Mobile drawer */}
      {openMobile && (
        <div className="lg:hidden fixed inset-0 z-40 flex" data-testid="mobile-drawer">
          <div className="w-[280px] max-w-[85vw]">{Sidebar}</div>
          <div className="flex-1 bg-black/50" onClick={() => setOpenMobile(false)} />
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="sticky top-0 z-30 h-16 border-b border-border bg-background/80 backdrop-blur-xl">
          <div className="h-full flex items-center gap-3 px-4 lg:px-8">
            <button
              className="lg:hidden p-2 -ml-2"
              onClick={() => setOpenMobile(true)}
              aria-label="Menu"
              data-testid="mobile-menu-toggle"
            >
              <List size={22} />
            </button>

            <div className="relative flex-1 max-w-xl">
              <Popover open={searchOpen} onOpenChange={setSearchOpen}>
                <PopoverTrigger asChild>
                  <div className="relative">
                    <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={searchQ}
                      onChange={(e) => { setSearchQ(e.target.value); setSearchOpen(true); }}
                      onFocus={() => setSearchOpen(true)}
                      placeholder={t("common.search")}
                      className="pl-9 rounded-sm h-9 bg-secondary/50 border-border font-mono-plex text-sm"
                      data-testid="topbar-global-search"
                    />
                  </div>
                </PopoverTrigger>
                {searchQ && (
                  <PopoverContent
                    align="start"
                    className="w-[520px] max-h-[70vh] overflow-y-auto p-0 rounded-sm"
                    onOpenAutoFocus={(e) => e.preventDefault()}
                  >
                    {searchRes.length === 0 ? (
                      <div className="p-4 text-sm text-muted-foreground">{t("common.no_results")}</div>
                    ) : (
                      <div className="divide-y divide-border">
                        {searchRes.map((r) => (
                          <button
                            key={`${r.collection}-${r.id}`}
                            onClick={() => { setSearchOpen(false); setSearchQ(""); navigate(r.link); }}
                            className="w-full flex items-start gap-3 p-3 text-left hover:bg-secondary"
                            data-testid={`search-result-${r.collection}-${r.id}`}
                          >
                            <Badge variant="outline" className="rounded-sm font-mono-plex text-[10px]">
                              {r.type}
                            </Badge>
                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-medium truncate">{r.title}</div>
                              <div className="text-xs text-muted-foreground truncate">{r.subtitle}</div>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </PopoverContent>
                )}
              </Popover>
            </div>

            {/* Notifications */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="relative p-2 hover:bg-secondary rounded-sm" data-testid="topbar-notifications">
                  <Bell size={20} weight="duotone" />
                  {notif.unread > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 h-4 min-w-4 px-1 rounded-full bg-[hsl(var(--brand-red))] text-white text-[10px] font-bold flex items-center justify-center">
                      {notif.unread}
                    </span>
                  )}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-80 rounded-sm">
                <DropdownMenuLabel className="overline">{t("notifications.title")}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {(notif.items || []).length === 0 ? (
                  <div className="p-4 text-sm text-muted-foreground">{t("notifications.empty")}</div>
                ) : (
                  notif.items.slice(0, 6).map((n) => (
                    <DropdownMenuItem key={n.id} className="flex flex-col items-start gap-0.5 py-2">
                      <span className="text-sm font-medium">{n.title}</span>
                      {n.body && <span className="text-xs text-muted-foreground line-clamp-2">{n.body}</span>}
                    </DropdownMenuItem>
                  ))
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate("/notifications")} data-testid="topbar-open-notifications">
                  Apri centro notifiche
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* User */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2 px-2 py-1 hover:bg-secondary rounded-sm" data-testid="topbar-user-menu">
                  <div className="h-8 w-8 rounded-sm bg-primary text-primary-foreground flex items-center justify-center font-mono-plex text-xs font-bold">
                    {initials}
                  </div>
                  <div className="hidden md:block text-left">
                    <div className="text-sm font-medium leading-tight">
                      {user?.first_name || user?.email?.split("@")[0]}
                    </div>
                    <div className="text-[10px] text-muted-foreground font-mono-plex">
                      {user?.is_superadmin ? "SUPER ADMIN" : "UTENTE"}
                    </div>
                  </div>
                  <CaretDown size={14} />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 rounded-sm">
                <DropdownMenuLabel className="text-xs">
                  <div className="text-sm font-medium truncate">{user?.email}</div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate("/change-password")} data-testid="user-menu-change-password">
                  {t("auth.change_password")}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate("/sessions")} data-testid="user-menu-sessions">
                  {t("sessions.title")}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout} data-testid="user-menu-logout">
                  <SignOut size={16} className="mr-2" /> {t("common.logout")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="flex-1 min-w-0 p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
