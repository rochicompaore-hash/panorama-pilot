import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

export default function SearchPage() {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const { data } = useQuery({
    queryKey: ["search-page", q],
    queryFn: async () => q ? (await api.get("/search", { params: { q } })).data : { results: [] },
    enabled: q.length > 0,
  });

  return (
    <div className="space-y-8" data-testid="search-page">
      <div>
        <div className="overline">{t("search.subtitle")}</div>
        <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("search.title")}</h1>
      </div>

      <Card className="rounded-sm border-border p-4">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search.placeholder")}
          className="rounded-sm h-11 max-w-2xl font-mono-plex" data-testid="search-input" />
      </Card>

      {q && (
        <Card className="rounded-sm border-border divide-y divide-border">
          {(data?.results || []).map((r) => (
            <button
              key={`${r.collection}-${r.id}`}
              onClick={() => navigate(r.link)}
              className="w-full text-left p-4 hover:bg-secondary flex items-start gap-4"
              data-testid={`search-page-result-${r.collection}-${r.id}`}
            >
              <Badge variant="outline" className="rounded-sm font-mono-plex text-[10px]">{r.type}</Badge>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium">{r.title}</div>
                <div className="text-xs text-muted-foreground truncate">{r.subtitle}</div>
              </div>
            </button>
          ))}
          {(data?.results || []).length === 0 && (
            <div className="p-10 text-center text-sm text-muted-foreground">{t("common.no_results")}</div>
          )}
        </Card>
      )}
    </div>
  );
}
