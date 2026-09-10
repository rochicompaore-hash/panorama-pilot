import React from "react";
import { useTranslation } from "react-i18next";

/**
 * Auth split-screen layout: photo left, form right.
 * Uses Manrope for display heading. Grain overlay for texture.
 */
export default function AuthLayout({ children, title, subtitle, testId }) {
  const { t } = useTranslation();
  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-[1.1fr_1fr] bg-background">
      {/* Left panel */}
      <div className="relative hidden lg:block overflow-hidden">
        <img
          src="https://images.unsplash.com/photo-1637088059539-ad62cba57895?auto=format&fit=crop&w=1600&q=80"
          alt=""
          aria-hidden="true"
          className="absolute inset-0 w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-zinc-950/70" />
        <div className="grain-overlay absolute inset-0" />
        <div className="relative z-10 h-full flex flex-col justify-between p-12 text-zinc-100">
          <div>
            <div className="overline text-zinc-400">Panorama Pilot</div>
            <div className="mt-2 text-3xl font-display font-black tracking-tight text-white">
              CLOUD ERP
            </div>
          </div>
          <div className="max-w-md">
            <div className="overline text-zinc-400 mb-4">Milestone 01 · Fondazioni</div>
            <h2 className="font-display text-4xl xl:text-5xl font-black tracking-tight leading-[1.05]">
              Precisione millimetrica.
              <br />
              <span className="text-blue-400">Nel serramento.</span>
              <br />
              Nel software.
            </h2>
            <p className="mt-6 text-sm text-zinc-400 leading-relaxed">
              Dal lead alla posa. Preventivi, produzione, magazzino, cantieri, incasso.
              Tutto in un'unica piattaforma, tracciata, granulare, italiana.
            </p>
          </div>
          <div className="flex items-center gap-6 text-xs text-zinc-500">
            <span className="overline">EUR · Europe/Rome</span>
            <span className="h-px flex-1 bg-zinc-700" />
            <span className="overline">v1.0 · M1</span>
          </div>
        </div>
      </div>

      {/* Right panel: form */}
      <div className="flex items-start lg:items-center justify-center px-6 py-12 lg:px-16" data-testid={testId}>
        <div className="w-full max-w-md">
          <div className="lg:hidden mb-8">
            <div className="overline">Panorama Pilot</div>
            <div className="font-display text-2xl font-black tracking-tight">CLOUD ERP</div>
          </div>
          <div className="mb-8">
            <div className="overline mb-3">{t("app.milestone")}</div>
            <h1 className="font-display text-3xl sm:text-4xl font-black tracking-tight">
              {title}
            </h1>
            {subtitle && (
              <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{subtitle}</p>
            )}
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
