import test from "node:test";
import assert from "node:assert/strict";
import logic from "../logic.js";

test("logic.js loads and exposes a placeholder version", () => {
  assert.equal(logic.version(), 0);
});
