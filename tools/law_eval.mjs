// SPDX-License-Identifier: Apache-2.0
// Evaluate a generated TF judge module (`bendeda/tf.py` renders it from
// model.bend plus one function per translated law) over a stimulus plan, and
// emit one record per model cycle.
//
// Why a driver rather than `bend` per trace: the judges are compiled once into
// this module, so a trace costs one `step` and N judge calls in JS instead of a
// checker invocation per law. The model side of TF is evaluation on a bound
// trace, not proof, and this is the evaluator the L1 vector path already relies
// on (same pinned compiler, same emitted module shape).
//
// Usage:
//   node tools/law_eval.mjs <judge.mjs> <plan.json> [--out cycles.json]
//
// Plan shape:
//   { "traces": [ { "ops": [ {"op": "Push", "din": 7}, {"op": "Pop"}, ... ] }, ... ],
//     "judges": [ { "fn": "tf_fifo_f07_pop_full_next_head", "params": ["state", "state"] } ] }
//
// A judge parameter is `state` or `din`. Bend bindings are affine, so a law that
// mentions the pre-state twice is compiled to two parameters; the driver passes
// the same value to each, which is duplication made explicit rather than a `dup`
// the surface syntax makes hard to write.
//
// Output shape:
//   { "module": "<path>", "runtime": "node <version>", "exports": [...],
//     "traces": [ [ { "cycle": 0, "op": "Push", "din": 7, "count": 1,
//                     "head": 7, "second": 0,
//                     "verdicts": { "tf_...": true } }, ... ], ... ] }
//
// A judge that throws is recorded as `{ "error": "<message>" }` for that cycle,
// not as `false`: an evaluator failure and a law that does not hold are
// different findings, and collapsing them would report a broken harness as a
// translation defect.
//
// Exit codes: 0 ok, 2 usage, 3 the module refused the call convention, 4 an
// entry point the plan needs is missing from the module.

import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import process from "node:process";

const [, , modulePath, planPath, ...rest] = process.argv;
if (!modulePath || !planPath) {
  console.error("usage: node law_eval.mjs <judge.mjs> <plan.json> [--out cycles.json]");
  process.exit(2);
}

const outIndex = rest.indexOf("--out");
const outPath = outIndex >= 0 ? rest[outIndex + 1] : null;

const plan = JSON.parse(readFileSync(planPath, "utf8"));
const judges = plan.judges ?? [];
if (!judges.length) {
  console.error("law_eval: the plan names no judge, so nothing would be evaluated");
  process.exit(2);
}

let ns;
try {
  ns = await import(pathToFileURL(modulePath).href);
} catch (error) {
  console.error(`law_eval: cannot import ${modulePath}: ${error.message}`);
  process.exit(3);
}

// Bend emits the defs as named exports on some versions and as one `default`
// object on others (2.0.40 does the latter). Same boundary as model_vectors.mjs.
const mod = ns && ns.default && typeof ns.default === "object" ? { ...ns.default } : ns;

const required = ["empty_fifo", "step", "count", "tf_head", "tf_second", ...judges.map((j) => j.fn)];
const missing = required.filter((name) => typeof mod[name] !== "function");
if (missing.length) {
  console.error(`law_eval: missing entry point(s) ${missing.join(", ")}`);
  console.error(`law_eval: the module exports ${Object.keys(mod).sort().join(", ") || "(none)"}`);
  process.exit(4);
}

// The emitted wrappers take live arguments either spread or as one array; try
// both and keep the one that answers a value. A function back means the
// convention was wrong and the wrapper is still waiting for arguments.
function call(name, args) {
  const fn = mod[name];
  for (const shape of [(f, a) => f(...a), (f, a) => f(a)]) {
    try {
      const value = shape(fn, args);
      if (typeof value !== "function") return value;
    } catch {
      // try the next convention
    }
  }
  throw new Error(`${name}(${args.length} args) refused both call conventions`);
}

const traces = [];
for (const trace of plan.traces ?? []) {
  let state = call("empty_fifo", []);
  const cycles = [];
  let index = 0;
  for (const spec of trace.ops ?? []) {
    const pre = state;
    const din = spec.din ?? null;
    const verdicts = {};
    for (const judge of judges) {
      const args = judge.params.map((kind) => (kind === "din" ? din : pre));
      try {
        verdicts[judge.fn] = call(judge.fn, args);
      } catch (error) {
        verdicts[judge.fn] = { error: error.message };
      }
    }
    const op = { $: spec.op };
    if (din !== null) op.din = din;
    state = call("step", [pre, op]);
    cycles.push({
      cycle: index,
      op: spec.op,
      din,
      count: call("count", [pre]),
      head: call("tf_head", [pre]),
      second: call("tf_second", [pre]),
      verdicts,
    });
    index += 1;
  }
  traces.push(cycles);
}

const payload = {
  module: modulePath,
  runtime: `node ${process.version}`,
  exports: Object.keys(mod).sort(),
  traces,
};

const text = JSON.stringify(payload) + "\n";
if (outPath) {
  writeFileSync(outPath, text, "utf8");
} else {
  process.stdout.write(text);
}
