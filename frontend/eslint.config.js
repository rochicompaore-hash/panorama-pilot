const react = require("eslint-plugin-react");
const reactHooks = require("eslint-plugin-react-hooks");

module.exports = [
  { ignores: ["node_modules/**", "build/**", "dist/**"] },
  {
    files: ["src/**/*.{js,jsx}"],
    plugins: { react, "react-hooks": reactHooks },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { window: "readonly", document: "readonly", console: "readonly", process: "readonly", setTimeout: "readonly", clearTimeout: "readonly", fetch: "readonly", URL: "readonly", Blob: "readonly", FormData: "readonly", localStorage: "readonly", navigator: "readonly", Intl: "readonly" },
    },
    settings: { react: { version: "detect" } },
    rules: { "react/jsx-uses-vars": "error", "react-hooks/rules-of-hooks": "error", "no-undef": "off", "no-unused-vars": "off" },
  },
];
