import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import it from "@/locales/it.json";

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { it: { translation: it } },
    lng: "it",
    fallbackLng: "it",
    supportedLngs: ["it"],
    interpolation: { escapeValue: false },
    detection: { order: ["querystring", "localStorage", "navigator"], caches: ["localStorage"] },
  });

export default i18n;
