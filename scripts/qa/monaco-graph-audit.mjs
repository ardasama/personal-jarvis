/**
 * Read-only Monaco module-graph profile for the OOM frontend build.
 * Uses the pinned frontend esbuild, preserves ALL editor/language registrations.
 * This is a graph measurement, not proof that Monaco caused the Vite OOM.
 */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const frontend = path.join(root, "jarvis/ui/web/frontend");
const editor = path.join(frontend, "src/components/agentic/editor");
const monaco = path.join(frontend, "node_modules/monaco-editor/esm/vs");
const require = createRequire(path.join(frontend, "package.json"));

const registerPaths = Object.freeze({
  languages: path.join(monaco, "languages/definitions/register.all.js"),
  features: path.join(monaco, "features/register.all.js"),
});

export function checkFeatureParity() {
  const runtime = fs.readFileSync(path.join(editor, "monacoRuntime.ts"), "utf8");
  const stage = fs.readFileSync(path.join(editor, "CodeEditorStage.tsx"), "utf8");
  const required = [
    'import "monaco-editor/features/register.all"',
    'import "monaco-editor/languages/definitions/register.all"',
    'import "monaco-editor/languages/features/json/register"',
    'import "monaco-editor/languages/features/css/register"',
    'import "monaco-editor/languages/features/html/register"',
    'from "monaco-editor/languages/features/typescript/register"',
    'from "monaco-editor/editor/editor.worker?worker"',
    'from "monaco-editor/languages/features/json/json.worker?worker"',
    'from "monaco-editor/languages/features/css/css.worker?worker"',
    'from "monaco-editor/languages/features/html/html.worker?worker"',
    'from "monaco-editor/languages/features/typescript/ts.worker?worker"',
  ];
  const missing = required.filter((value) => !runtime.includes(value));
  if (!stage.includes('lazy(() => import("./EditorSurface"))')) {
    missing.push("lazy EditorSurface import");
  }
  if (missing.length) throw new Error("Monaco feature parity changed: " + missing.join(", "));
  const languageRegistry = fs.readFileSync(registerPaths.languages, "utf8");
  const featureRegistry = fs.readFileSync(registerPaths.features, "utf8");
  const imports = {
    languages: (languageRegistry.match(/^import /gm) ?? []).length,
    features: (featureRegistry.match(/^import /gm) ?? []).length,
  };
  if (imports.languages < 50 || imports.features < 50) {
    throw new Error("Unexpected Monaco registration count; update parity audit");
  }
  return { imports, workerTypes: 5, lazyEditorSurface: true };
}

export async function profileMonacoGraph() {
  const { build } = require("esbuild");
  const result = {};
  for (const [name, entry] of Object.entries(registerPaths)) {
    const started = Date.now();
    const bundle = await build({
      entryPoints: [entry],
      bundle: true,
      write: false,
      metafile: true,
      format: "esm",
      platform: "browser",
      target: "es2022",
      logLevel: "silent",
      loader: { ".css": "empty", ".svg": "empty", ".ttf": "empty", ".woff": "empty", ".woff2": "empty" },
    });
    const inputs = Object.values(bundle.metafile.inputs);
    result[name] = {
      modules: inputs.length,
      sourceBytes: inputs.reduce((sum, item) => sum + item.bytes, 0),
      emittedBytes: bundle.outputFiles.reduce((sum, file) => sum + file.contents.byteLength, 0),
      elapsedMs: Date.now() - started,
    };
  }
  return result;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const parity = checkFeatureParity();
  const graphs = await profileMonacoGraph();
  process.stdout.write(JSON.stringify({ parity, graphs }) + "\n");
}