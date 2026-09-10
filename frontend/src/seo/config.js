export const SEO = {
  siteName: "Panorama Pilot",
  baseTitle: "Panorama Pilot",
  defaultDescription: "Gestionale per aziende di serramenti, preventivi, clienti, cantieri e commesse.",
  homeDescription:
    "Panorama Pilot è il software gestionale per aziende di serramenti: CRM, preventivi, contratti, cantieri, clienti, documenti e gestione della commessa in un'unica piattaforma.",
  ogImagePath: "/og-image.png",
  twitterCard: "summary_large_image",
  locale: "it_IT",
  publicPaths: ["/landing"],
};

export const baseUrl = () => (typeof window !== "undefined" ? window.location.origin : "");
export const pageTitle = (t) => (t ? `${t} | ${SEO.siteName}` : SEO.baseTitle);
