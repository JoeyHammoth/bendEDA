// SPDX-License-Identifier: Apache-2.0
// Drive a compiled Bend model (`bend model.bend -o model.mjs`) with a
// deterministic stimulus plan and emit `vectors.json`.
//
// Why this exists: the L1 trace-conformance rung is only meaningful if the
// reference model can actually be *executed*, not merely checked. The design
// document's Appendix K (G-03) fixes this as the path; this script is the
// executable half of it.
//
// Usage:
//   node tools/model_vectors.mjs <model.mjs> <plan.json> [--out vectors.json]
//
// Plan shape, counter-shaped (the original):
//   { "count0": 0, "incs": [1, 2, ...], "entries": ["step", "run"] }
//
// Plan shape, algebraic: one model constructor per cycle, observed through a
// model function, so a design whose input is an ADT is executable too:
//   { "ops": [{ "op": "Push", "din": 7 }, { "op": "Pop" }, ...],
//     "init": "empty_fifo", "observe": "dout" }
//
// Output shape:
//   { "model": "<path>", "count0": 0, "steps": [{ "inc": 1, "out": 1 }, ...],
//     "run": 15, "exports": ["limb", "step", "run"], "runtime": "node <version>" }
//
// Exit codes: 0 ok, 2 usage, 3 the module refused the call convention, 4 an
// entry point named in the plan is missing from the module.

import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import process from "node:process";

const [, , modulePath, planPath, ...rest] = process.argv;
if (!modulePath || !planPath) {
  console.error("usage: node model_vectors.mjs <model.mjs> <plan.json> [--out vectors.json]");
  process.exit(2);
}

const outIndex = rest.indexOf("--out");
const outPath = outIndex >= 0 ? rest[outIndex + 1] : null;

const plan = JSON.parse(readFileSync(planPath, "utf8"));
const count0 = plan.count0 ?? 0;
const incs = plan.incs ?? [];
// An ops plan needs `step` only: `run` folds the counter's input list and has no
// meaning for an operation sequence, so requiring it would reject a valid model.
const wanted = plan.ops ? ["step"] : plan.entries ?? ["step", "run"];

// A Bend constructor crosses as {$: "Name", field: value}, and the field names
// are the *compiled* ones, not the names used in the source pattern: the model
// writes `case Con{h, t}` but the emitted module reads `["head"]` and `["tail"]`.
// Building the source names yields a silently empty argument; building these
// reads `undefined.$` on the tail. Hence the explicit erased-name test in
// tests/test_vector_path.py — this boundary is not guessable.
function listOf(values) {
  let acc = { $: "Nil" };
  for (let i = values.length - 1; i >= 0; i -= 1) {
    acc = { $: "Con", head: values[i], tail: acc };
  }
  return acc;
}

let ns;
try {
  ns = await import(pathToFileURL(modulePath).href);
} catch (error) {
  console.error(`model_vectors: cannot import ${modulePath}: ${error.message}`);
  process.exit(3);
}

// Bend emits the defs as named exports on some versions and as one `default`
// object on others (2.0.40 does the latter). Support both rather than pinning the
// driver to a compiler detail that has already changed once.
const mod = ns && ns.default && typeof ns.default === "object" ? { ...ns.default } : ns;

const exportsSeen = Object.keys(mod).sort();
const missing = wanted.filter((name) => typeof mod[name] !== "function");
if (missing.length) {
  console.error(`model_vectors: missing entry point(s) ${missing.join(", ")}`);
  console.error(`model_vectors: module exports ${exportsSeen.join(", ") || "(none)"}`);
  process.exit(4);
}

// The emitted module wraps each def so a JS caller passes live arguments "in one
// call or curried". Rather than guess, try the two shapes and keep the one that
// answers a value; a silent wrong-convention call would be worse than a failure.
const callers = [
  ["spread", (fn, args) => fn(...args)],
  ["array", (fn, args) => fn(args)],
  // A curried wrapper answers a function; calling it per argument either returns
  // the value or another function to call. This shape appears when the wrapper
  // is built for a caller that supplies arguments one at a time.
  [
    "curried",
    (fn, args) => args.reduce((acc, arg) => (typeof acc === "function" ? acc(arg) : acc), fn),
  ],
];

function invoke(name, args) {
  const fn = mod[name];
  const errors = [];
  for (const [label, call] of callers) {
    try {
      const value = call(fn, args);
      // A function here means the convention was wrong and the wrapper is still
      // waiting for arguments. Accepting it would silently serialise to nothing
      // in the JSON output — a missing key, not an error, which is the worst
      // failure mode for a conformance tool.
      if (value !== undefined && typeof value !== "function") return { value, convention: label };
    } catch (error) {
      errors.push(`${label}: ${error.message}`);
    }
  }
  console.error(`model_vectors: ${name}(${args.length} args) refused both conventions:`);
  for (const line of errors) console.error(`  ${line}`);
  process.exit(3);
}

let convention = null;
function run(name, args) {
  const result = invoke(name, args);
  convention = convention ?? result.convention;
  return result.value;
}

let result;
if (plan.ops) {
  // Algebraic stimulus: the state is opaque to this driver and is threaded through
  // `step` exactly as the model defines it. The constructor field names are the
  // ones the model writes (`din`, not a renamed field), so a spec carries them as
  // written; the list case above is the one where the compiler renames fields.
  const observe = plan.observe ?? "dout";
  const init = plan.init ?? "empty_fifo";
  for (const name of [init, observe]) {
    if (typeof mod[name] !== "function") {
      console.error(`model_vectors: plan needs ${name}(), which the module does not export`);
      console.error(`model_vectors: module exports ${exportsSeen.join(", ") || "(none)"}`);
      process.exit(4);
    }
  }
  const steps = [];
  let state = run(init, []);
  for (const spec of plan.ops) {
    const { op, ...fields } = spec;
    state = run("step", [state, { $: op, ...fields }]);
    const value = run(observe, [state]);
    if (typeof value !== "number") {
      console.error(`model_vectors: ${observe}() answered a value this driver cannot compare`);
      process.exit(3);
    }
    steps.push({ op, out: value });
  }
  result = {
    model: modulePath,
    ops: plan.ops.length,
    steps,
    exports: exportsSeen,
    convention,
    runtime: `node ${process.version}`,
  };
} else {
  // `run` folds the whole input list in one call; `step` is walked cycle by cycle
  // so a one-cycle offset in the DUT is visible rather than smoothed out.
  const steps = [];
  let count = count0;
  for (const inc of incs) {
    count = run("step", [count, inc]);
    steps.push({ inc, out: count });
  }

  result = {
    model: modulePath,
    count0,
    steps,
    exports: exportsSeen,
    convention,
    runtime: `node ${process.version}`,
  };

  if (wanted.includes("run")) {
    result.run = run("run", [listOf(incs), count0]);
  }
  if (typeof mod.limb === "function") {
    result.limb = run("limb", []);
  }
}

const text = JSON.stringify(result, null, 2);
if (outPath) {
  writeFileSync(outPath, text + "\n", "utf8");
} else {
  process.stdout.write(text + "\n");
}
