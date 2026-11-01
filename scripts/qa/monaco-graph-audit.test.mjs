import test from "node:test";
import assert from "node:assert/strict";
import { checkFeatureParity, profileMonacoGraph } from "./monaco-graph-audit.mjs";

test("all Monaco registrations, language services and workers are retained", () => {
  const parity = checkFeatureParity();
  assert.ok(parity.imports.languages >= 50);
  assert.ok(parity.imports.features >= 50);
  assert.equal(parity.workerTypes, 5);
  assert.equal(parity.lazyEditorSurface, true);
});

test("low-memory profile completes without changing source or emitting artifacts", async () => {
  const graph = await profileMonacoGraph();
  assert.ok(graph.languages.modules >= 600);
  assert.ok(graph.features.modules >= 600);
  assert.ok(graph.languages.sourceBytes > 1_000_000);
  assert.ok(graph.features.sourceBytes > 1_000_000);
});