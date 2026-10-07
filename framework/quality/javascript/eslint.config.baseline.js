// Baseline ESLint flat config for React/JS/TS projects under this framework.
//
// Copy to eslint.config.js at the project root (or merge if one already
// exists) and add a "lint": "eslint ." script to package.json -- G4 only
// runs `npm run lint`, it never invents one, so without that script this
// config is inert no matter how good it is.
//
// package.json must pin these (verified during this framework's audit):
//   "devDependencies": {
//     "eslint": "^9",                        <- NOT ^10. eslint-plugin-react
//                                                7.37.5 (current as of this
//                                                writing) declares a peer dep
//                                                capped at eslint ^9.7 and
//                                                crashes at runtime
//                                                (TypeError in
//                                                react/display-name) under
//                                                ESLint 10 if npm is allowed
//                                                to resolve past that cap
//                                                with --legacy-peer-deps.
//                                                Reproduced directly: this
//                                                is not a hypothetical.
//     "eslint-plugin-react": "^7.37",
//     "eslint-plugin-react-hooks": "^7",
//     "eslint-plugin-jsx-a11y": "^6.10",
//     "@eslint/js": "^9",
//     "globals": "^15"
//   }
//
// Verified catches (against a component with a conditional hook call, a
// console.log of a hardcoded key, an onClick with no keyboard equivalent,
// and a missing prop-types declaration): react-hooks/rules-of-hooks,
// jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-
// interactions, react/prop-types, no-console. It does NOT catch the
// hardcoded key itself -- that's gitleaks' job (framework/gates/
// g4_executable.sh's secrets section), not ESLint's; no core or
// react-plugin rule here does secret-shape detection.
const js = require("@eslint/js");
const react = require("eslint-plugin-react");
const reactHooks = require("eslint-plugin-react-hooks");
const jsxA11y = require("eslint-plugin-jsx-a11y");
const globals = require("globals");

module.exports = [
  js.configs.recommended,
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    plugins: { react, "react-hooks": reactHooks, "jsx-a11y": jsxA11y },
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser, ...globals.node },
    },
    settings: { react: { version: "detect" } },
    rules: {
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,
      "react/react-in-jsx-scope": "off", // not needed with the modern JSX transform
      "no-magic-numbers": ["warn", { ignore: [0, 1, -1], ignoreArrayIndexes: true }],
      "no-console": "warn",
      "no-debugger": "error",
    },
  },
];
