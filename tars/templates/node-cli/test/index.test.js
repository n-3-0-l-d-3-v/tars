import { test } from "node:test";
import assert from "node:assert/strict";
import { greet } from "../src/index.js";

test("greet includes the project name", () => {
  assert.ok(greet("World").includes("__TARS_PROJECT_NAME__"));
});

test("greet includes the given name", () => {
  assert.ok(greet("Ada").includes("Ada"));
});
