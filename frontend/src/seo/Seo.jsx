import { useEffect } from "react";
import { SEO, baseUrl, pageTitle } from "./config";

function setMeta(attr, key, content) {
  let el = document.head.querySelector(`meta[${attr}="${key}"]`);
  if (!el) { el = document.createElement("meta"); el.setAttribute(attr, key); document.head.appendChild(el); }
  el.setAttribute("content", content);
}

function setLink(rel, href) {
  let el = document.head.querySelector(`link[rel="${rel}"]`);
  if (!el) { el = document.createElement("link"); el.setAttribute("rel", rel); document.head.appendChild(el); }
  el.setAttribute("href", href);
}

function setJsonLd(data) {
  let el = document.getElementById("seo-jsonld");
  if (!data) { el?.remove(); return; }
  if (!el) { el = document.createElement("script"); el.id = "seo-jsonld"; el.type = "application/ld+json"; document.head.appendChild(el); }
  el.textContent = JSON.stringify(data);
}

/** Metadata centralizzati per pagina. Default fail-safe: noindex. */
export function Seo({ title, description, path, index = false, jsonLd = null }) {
  useEffect(() => {
    const origin = baseUrl();
    const url = `${origin}${path || window.location.pathname}`;
    const fullTitle = pageTitle(title);
    const desc = description || SEO.defaultDescription;
    document.documentElement.lang = "it";
    document.title = fullTitle;
    setMeta("name", "description", desc);
    setMeta("name", "robots", index ? "index, follow" : "noindex, nofollow");
    setLink("canonical", url);
    setMeta("property", "og:type", "website");
    setMeta("property", "og:site_name", SEO.siteName);
    setMeta("property", "og:locale", SEO.locale);
    setMeta("property", "og:title", fullTitle);
    setMeta("property", "og:description", desc);
    setMeta("property", "og:url", url);
    setMeta("property", "og:image", `${origin}${SEO.ogImagePath}`);
    setMeta("name", "twitter:card", SEO.twitterCard);
    setMeta("name", "twitter:title", fullTitle);
    setMeta("name", "twitter:description", desc);
    setMeta("name", "twitter:image", `${origin}${SEO.ogImagePath}`);
    setJsonLd(jsonLd);
  }, [title, description, path, index, jsonLd]);
  return null;
}

export const homeJsonLd = () => ({
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: SEO.siteName,
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  inLanguage: "it",
  description: SEO.homeDescription,
  url: `${baseUrl()}/landing`,
});
