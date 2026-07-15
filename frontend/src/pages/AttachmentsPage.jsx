import React, { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { API_BASE, api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "sonner";
import { CloudArrowUp, DownloadSimple, Trash, Paperclip } from "@phosphor-icons/react";

function formatSize(bytes) {
  if (!bytes) return "0 B";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0; let v = bytes;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${u[i]}`;
}

export default function AttachmentsPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const fileRef = useRef(null);
  const [entityType, setEntityType] = useState("document");
  const [tags, setTags] = useState("");
  const [description, setDescription] = useState("");
  const [q, setQ] = useState("");

  const { data } = useQuery({
    queryKey: ["attachments", q],
    queryFn: async () => (await api.get("/attachments", { params: { q: q || undefined } })).data,
  });

  const uploadMut = useMutation({
    mutationFn: async (file) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("entity_type", entityType || "document");
      if (tags) fd.append("tags", tags);
      if (description) fd.append("description", description);
      const tok = localStorage.getItem("ie_access_token");
      const { data } = await axios.post(`${API_BASE}/attachments/upload`, fd, {
        withCredentials: true,
        headers: {
          Authorization: tok ? `Bearer ${tok}` : undefined,
        },
      });
      return data;
    },
    onSuccess: () => { toast.success(t("toast.created")); qc.invalidateQueries({ queryKey: ["attachments"] }); setTags(""); setDescription(""); if (fileRef.current) fileRef.current.value = ""; },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  const deleteMut = useMutation({
    mutationFn: async (id) => (await api.delete(`/attachments/${id}`)).data,
    onSuccess: () => { toast.success(t("toast.deleted")); qc.invalidateQueries({ queryKey: ["attachments"] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  const download = async (a) => {
    try {
      const tok = localStorage.getItem("ie_access_token");
      const res = await axios.get(`${API_BASE}/attachments/${a.id}/download`, {
        withCredentials: true,
        responseType: "blob",
        headers: { Authorization: tok ? `Bearer ${tok}` : undefined },
      });
      const url = URL.createObjectURL(res.data);
      const link = document.createElement("a");
      link.href = url; link.download = a.filename; link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || e.message);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) uploadMut.mutate(f);
  };

  return (
    <div className="space-y-8" data-testid="attachments-page">
      <div>
        <div className="overline">{t("attachments.subtitle")}</div>
        <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("attachments.title")}</h1>
      </div>

      {has("attachments.create") && (
        <Card className="rounded-sm border-border p-6" data-testid="upload-card">
          <div className="overline mb-4">{t("attachments.upload")}</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div className="space-y-1.5">
              <Label className="overline">{t("attachments.entity_type")}</Label>
              <Input value={entityType} onChange={(e) => setEntityType(e.target.value)} className="rounded-sm h-10" data-testid="upload-entity-type" />
            </div>
            <div className="space-y-1.5">
              <Label className="overline">{t("attachments.tags")}</Label>
              <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="es. contratto, 2026" className="rounded-sm h-10" data-testid="upload-tags" />
            </div>
            <div className="space-y-1.5">
              <Label className="overline">{t("attachments.description")}</Label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} className="rounded-sm h-10" data-testid="upload-description" />
            </div>
          </div>
          <div
            className="border-2 border-dashed border-border p-10 text-center cursor-pointer hover:border-foreground transition-colors"
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={onDrop}
            data-testid="upload-dropzone"
          >
            <CloudArrowUp size={40} className="mx-auto text-muted-foreground mb-3" weight="duotone" />
            <div className="text-sm">{t("attachments.drop_here")}</div>
            <input
              ref={fileRef}
              type="file"
              hidden
              onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadMut.mutate(f); }}
              data-testid="upload-file-input"
            />
          </div>
        </Card>
      )}

      <Card className="rounded-sm border-border p-4">
        <Input placeholder={t("common.search")} value={q} onChange={(e) => setQ(e.target.value)} className="rounded-sm h-10 max-w-sm" data-testid="attachments-search" />
      </Card>

      <Card className="rounded-sm border-border overflow-x-auto" data-testid="attachments-table">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="overline">{t("attachments.filename")}</TableHead>
              <TableHead className="overline">{t("attachments.entity_type")}</TableHead>
              <TableHead className="overline">{t("attachments.tags")}</TableHead>
              <TableHead className="overline">{t("attachments.size")}</TableHead>
              <TableHead className="overline">{t("common.created_at")}</TableHead>
              <TableHead className="overline text-right">{t("common.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data?.items || []).map((a) => (
              <TableRow key={a.id} data-testid={`attachment-row-${a.id}`}>
                <TableCell className="font-medium flex items-center gap-2"><Paperclip size={14} />{a.filename}</TableCell>
                <TableCell><span className="text-xs font-mono-plex bg-secondary px-2 py-0.5">{a.entity_type}</span></TableCell>
                <TableCell className="text-xs">{(a.tags || []).join(", ") || "—"}</TableCell>
                <TableCell className="font-mono-plex text-xs">{formatSize(a.size)}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{a.created_at ? new Date(a.created_at).toLocaleString("it-IT") : "—"}</TableCell>
                <TableCell className="text-right">
                  {has("attachments.download") && (
                    <Button variant="outline" size="sm" className="rounded-sm mr-2 gap-1" onClick={() => download(a)} data-testid={`attachment-download-${a.id}`}>
                      <DownloadSimple size={12} />{t("common.download")}
                    </Button>
                  )}
                  {has("attachments.delete") && (
                    <Button
                      variant="outline" size="sm"
                      className="rounded-sm text-destructive hover:text-destructive"
                      onClick={() => { if (window.confirm(t("attachments.delete_confirm", { name: a.filename }))) deleteMut.mutate(a.id); }}
                      data-testid={`attachment-delete-${a.id}`}
                    ><Trash size={12} /></Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {(data?.items || []).length === 0 && (
              <TableRow><TableCell colSpan={6} className="text-center py-10 text-sm text-muted-foreground">{t("attachments.no_files")}</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
