const path = require("path");
const cfg = require(path.join(__dirname, "frontend", "eslint.config.js"));
module.exports = cfg.map((c) => (c.files ? { ...c, files: c.files.map((f) => `frontend/${f}`) } : { ...c, ignores: [...(c.ignores || []), "backend/**", "**/node_modules/**"] }));
