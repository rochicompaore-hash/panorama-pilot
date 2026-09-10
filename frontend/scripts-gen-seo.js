/* Genera robots.txt e sitemap.xml con l'URL pubblico reale (REACT_APP_PUBLIC_BASE_URL o REACT_APP_BACKEND_URL). */
const fs = require("fs");
const path = require("path");
require("dotenv").config({ path: path.join(__dirname, ".env") });
const base = (process.env.REACT_APP_PUBLIC_BASE_URL || process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
if (!base) { console.error("gen-seo: REACT_APP_BACKEND_URL mancante"); process.exit(1); }
for (const f of ["robots.txt", "sitemap.xml"]) {
  const tpl = fs.readFileSync(path.join(__dirname, "seo-templates", `${f}.tpl`), "utf8");
  fs.writeFileSync(path.join(__dirname, "public", f), tpl.replace(/__BASE_URL__/g, base));
}
console.log("gen-seo: robots.txt + sitemap.xml ->", base);
