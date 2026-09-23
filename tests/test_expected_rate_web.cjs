"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const bundlePath = process.env.GOEDUSPLIT_WEB_BUNDLE || path.join(__dirname, "../app/spliter_ox_web/assets/index-DE5gZsFK.js");
const source = fs.readFileSync(bundlePath, "utf8");
const start = source.indexOf(",F=[`A`,`B`,`C`,`D`,`E`]");
const end = source.indexOf("function qa(){", start);
assert.ok(start > 0 && end > start, "locate application helpers outside the React runtime");
const context = vm.createContext({});
vm.runInContext("const " + source.slice(start + 1, end) + ";globalThis.helpers={F,ji,Hi,Ui,Wi,Yi,Ri,ta,aa,oa,Wa,Ga,goeduEditRate,goeduPrepareRate,goeduReadProject,goeduSerializeProject};", context, { filename: bundlePath });
const api = context.helpers;
const clone = value => JSON.parse(JSON.stringify(value));
const levels = ["A", "B", "C", "D", "E"];

function project() {
  const judges = [{ id: "judge-1", name: "Review 1" }, { id: "judge-2", name: "Review 2" }];
  const item = api.Yi(1, judges, { id: "item-1", points: 1, targetLevel: "C", type: "선택형", difficulty: "보통", sampleSize: 3 });
  for (const judge of judges) {
    for (const level of levels) item.judgmentsByJudge[judge.id][level] = { correct: [true, true, false], targetRate: 63.25, overrideRate: judge.id === "judge-1" ? null : 63.25 };
  }
  return clone({ version: 1, judges, activeJudgeId: "judge-2", items: [item], evidenceData: null, evidenceMode: "difficultyAverage", targetRatePresets: null });
}

function near(actual, expected) {
  assert.ok(Math.abs(actual - expected) < 1e-12, `${actual} differs from ${expected}`);
}

function freeze(value) {
  if (value && typeof value === "object") {
    Object.freeze(value);
    for (const child of Object.values(value)) freeze(child);
  }
  return value;
}

test("the complete bundle parses without executing React or the NEIS IIFE", () => {
  new vm.Script(source, { filename: bundlePath });
  assert.equal("window" in context, false);
  assert.equal("React" in context, false);
});

test("O/X ratios and manual fractional rates retain calculation precision", () => {
  const input = project(), item = input.items[0];
  assert.equal(api.Hi(item.judgmentsByJudge["judge-1"].C), 2 / 3 * 100);
  assert.equal(api.Hi(item.judgmentsByJudge["judge-2"].C), 63.25);
  const rate = (2 / 3 * 100 + 63.25) / 2;
  near(api.ta(item, input.judges).C, rate);
  near(api.aa(input.items, input.judges).C, rate / 100);
  near(api.oa(input.items, "judge-1").C, 2 / 3);
  near(api.oa(input.items, "judge-2").C, 0.6325);
});

test("editing target and override rates preserves decimals, zero and 100", () => {
  const input = freeze({ correct: [true, true, false], targetRate: 70, overrideRate: null });
  for (const rate of [0, 63.25, 2 / 3 * 100, 100]) {
    const updated = api.goeduEditRate(api.goeduEditRate(input, "targetRate", rate), "overrideRate", rate);
    assert.equal(updated.targetRate, rate);
    assert.equal(updated.overrideRate, rate);
    assert.equal(api.Hi(updated), rate);
  }
  const cleared = api.goeduEditRate(input, "overrideRate", null);
  assert.equal(api.Hi(cleared), 2 / 3 * 100);
  assert.equal(input.targetRate, 70);
  for (const invalid of [-1, 100.01, NaN, Infinity, "63.25"]) assert.throws(() => api.goeduEditRate(input, "overrideRate", invalid), /숫자/);
});

test("default two-thirds is a suggestion; explicit target conversion can be zero", () => {
  assert.equal(api.Wi(0, 3, "C", "C").correct.filter(Boolean).length, 2);
  assert.equal(api.Ui(0, 3).filter(Boolean).length, 0);
  assert.equal(api.Ui(100, 3).filter(Boolean).length, 3);
  assert.equal(api.Ui(49.6, 1).filter(Boolean).length, 0);
  assert.ok(source.includes("correct:Ui(e.targetRate,e.correct.length)"));
  assert.ok(source.includes("let i=goeduPrepareRate(`targetRate`,r);if(i.error){window.alert(i.error);return}je("));
  assert.ok(source.includes("let i=goeduPrepareRate(`overrideRate`,r);if(i.error){window.alert(i.error);return}je("));
});

test("JSON save/load and Ga/Wa do not alter judgment data or force 100 to 95", () => {
  const input = project();
  input.items[0].judgmentsByJudge["judge-2"].A.overrideRate = 100;
  input.items[0].judgmentsByJudge["judge-2"].A.targetRate = 100;
  input.items[0].judgmentsByJudge["judge-1"].E.correct = [false, false, false];
  freeze(input);
  const before = JSON.stringify(input);
  const imported = api.Ga(input.items, input.judges);
  api.Wa(imported, input.judges);
  assert.equal(JSON.stringify(input), before);
  assert.deepEqual(clone(imported[0].judgmentsByJudge), input.items[0].judgmentsByJudge);
  const loaded = api.goeduReadProject(JSON.parse(api.goeduSerializeProject(input)));
  assert.equal(loaded.activeJudgeId, "judge-2");
  assert.deepEqual(clone(loaded.items[0].judgmentsByJudge), input.items[0].judgmentsByJudge);
  near(api.aa(loaded.items, loaded.judges).C, (2 / 3 * 100 + 63.25) / 200);
  assert.equal(api.Hi(loaded.items[0].judgmentsByJudge["judge-2"].A), 100);
  loaded.items[0].judgmentsByJudge["judge-2"].C.overrideRate = 20;
  assert.equal(input.items[0].judgmentsByJudge["judge-2"].C.overrideRate, 63.25);
});

test("empty project roundtrip clears items and selection", () => {
  const input = project();
  input.items = [];
  const result = api.goeduReadProject(JSON.parse(api.goeduSerializeProject(input)));
  assert.deepEqual(clone(result.items), []);
  assert.deepEqual(clone(result.selectedIds), []);
  assert.equal(result.selectedId, "");
  assert.equal(api.aa(result.items, result.judges).C, 0);
  assert.equal(result.activeJudgeId, "judge-2");
});

test("exact rates and split scores agree with the shared expected-rates module", () => {
  const shared = require(process.env.GOEDUSPLIT_EXPECTED_RATES_MODULE || path.join(path.dirname(bundlePath), "../expected-rates.js"));
  const input = api.goeduReadProject(JSON.parse(api.goeduSerializeProject(project())));
  for (const judge of input.judges) {
    for (const level of levels) {
      const cell = input.items[0].judgmentsByJudge[judge.id][level];
      assert.equal(api.Hi(cell), shared.cellRate(cell));
    }
  }
  const summary = shared.summarize(input);
  for (const level of levels) {
    near(api.ta(input.items[0], input.judges)[level], shared.designsFromProject(input)[0].rates[level]);
    near(api.aa(input.items, input.judges)[level], summary.raw_cuts[level]);
  }
});

test("100 percent O/X and zero overrides survive saving without correction", () => {
  const input = project();
  input.items[0].judgmentsByJudge["judge-1"].C.correct = [true, true, true];
  input.items[0].judgmentsByJudge["judge-2"].C.overrideRate = 0;
  const loaded = api.goeduReadProject(JSON.parse(api.goeduSerializeProject(input)));
  assert.equal(api.Hi(loaded.items[0].judgmentsByJudge["judge-1"].C), 100);
  assert.equal(api.Hi(loaded.items[0].judgmentsByJudge["judge-2"].C), 0);
  assert.equal(api.ta(loaded.items[0], loaded.judges).C, 50);
});

test("numbering is unique within item type, with independent selected/constructed numbers", () => {
  const input = project();
  const second = clone(input.items[0]);
  second.id = "item-2";
  second.type = "서답형";
  input.items.push(second);
  assert.equal(api.goeduReadProject(input).items.length, 2);
  second.type = "선택형";
  assert.throws(() => api.goeduReadProject(input), /중복 문항 번호/);
  second.type = "서답형";
  second.id = "item-1";
  assert.throws(() => api.goeduReadProject(input), /중복 문항 ID/);
});

test("missing legacy judgments receive defaults while omitted override uses O/X", () => {
  const input = project();
  delete input.items[0].judgmentsByJudge;
  const result = api.goeduReadProject(input);
  assert.equal(result.items[0].judgmentsByJudge["judge-1"].C.correct.filter(Boolean).length, 2);
  const legacy = project();
  delete legacy.items[0].judgmentsByJudge["judge-1"].C.overrideRate;
  assert.equal(api.Hi(api.goeduReadProject(legacy).items[0].judgmentsByJudge["judge-1"].C), 2 / 3 * 100);
});

const invalidCases = [
  ["negative override", p => p.items[0].judgmentsByJudge["judge-1"].C.overrideRate = -1],
  ["override over 100", p => p.items[0].judgmentsByJudge["judge-1"].C.overrideRate = 101],
  ["NaN override", p => p.items[0].judgmentsByJudge["judge-1"].C.overrideRate = NaN],
  ["infinite override", p => p.items[0].judgmentsByJudge["judge-1"].C.overrideRate = Infinity],
  ["string override", p => p.items[0].judgmentsByJudge["judge-1"].C.overrideRate = "63.25"],
  ["negative target", p => p.items[0].judgmentsByJudge["judge-1"].C.targetRate = -1],
  ["target over 100", p => p.items[0].judgmentsByJudge["judge-1"].C.targetRate = 101],
  ["NaN target", p => p.items[0].judgmentsByJudge["judge-1"].C.targetRate = NaN],
  ["null target", p => p.items[0].judgmentsByJudge["judge-1"].C.targetRate = null],
  ["negative points", p => p.items[0].points = -0.1],
  ["NaN points", p => p.items[0].points = NaN],
  ["string points", p => p.items[0].points = "4"],
  ["non-boolean correct", p => p.items[0].judgmentsByJudge["judge-1"].C.correct = [true, true, 0]],
  ["null correct", p => p.items[0].judgmentsByJudge["judge-1"].C.correct = null],
  ["mismatched sample", p => p.items[0].sampleSize = 4],
  ["fractional sample", p => p.items[0].sampleSize = 2.5],
  ["missing level", p => delete p.items[0].judgmentsByJudge["judge-1"].C],
  ["null judgments", p => p.items[0].judgmentsByJudge = null],
  ["zero number", p => p.items[0].number = 0],
  ["fractional number", p => p.items[0].number = 1.5],
  ["empty item ID", p => p.items[0].id = ""],
  ["duplicate judge ID", p => p.judges[1].id = p.judges[0].id],
  ["prototype judge ID", p => p.judges[0].id = "__proto__"],
  ["missing items", p => delete p.items],
  ["null items", p => p.items = null],
  ["object items", p => p.items = {}],
  ["empty judges", p => p.judges = []],
  ["invalid presets", p => p.targetRatePresets = { A: { A: 101 } }],
];

for (const [label, corrupt] of invalidCases) {
  test("reject before mutation/serialization: " + label, () => {
    const input = project();
    corrupt(input);
    freeze(input);
    let current = project();
    const prior = current;
    assert.throws(() => { current = api.goeduReadProject(input); }, error => typeof error.message === "string" && error.message.length > 0);
    assert.equal(current, prior);
    assert.throws(() => api.goeduSerializeProject(input));
    assert.equal("__GOEDUSPLIT_TARGET_RATE_PRESETS__" in context, false);
  });
}

test("JSON numeric overflow is rejected and malformed JSON never reaches import", () => {
  const input = project();
  input.items[0].judgmentsByJudge["judge-1"].C.overrideRate = 12.345;
  const json = JSON.stringify(input).replace('"overrideRate":12.345', '"overrideRate":1e999');
  assert.throws(() => api.goeduReadProject(JSON.parse(json)), /숫자/);
  assert.throws(() => JSON.parse('{"items":NaN}'), SyntaxError);
});

test("file and bridge entry points validate before applying state or presets", () => {
  const fileGuard = source.indexOf("let n=goeduReadProject(e);e.targetRatePresets&&");
  assert.ok(fileGuard > end);
  const setter = source.indexOf("globalThis.__GOEDUSPLIT_TARGET_RATE_PRESETS__=e.targetRatePresets", fileGuard);
  assert.ok(setter > fileGuard);
  assert.ok(source.indexOf("D(n)}else{", setter) > setter);
  assert.ok(source.includes("try{D(goeduReadProject(e))}catch(e){window.alert("));
  assert.ok(source.includes("n(o.__GOEDUSPLIT_PROJECT__)||e(o.__GOEDUSPLIT_EVIDENCE__)"));
  assert.ok(source.includes("va(`expected-rate-project.json`,goeduSerializeProject("));
});

test("invalid UI rates are reported before a deferred updater can be scheduled", () => {
  for (const field of ["targetRate", "overrideRate"]) {
    const before = freeze({ correct: [true, true, false], targetRate: 63.25, overrideRate: 63.25 });
    for (const invalid of [101, -1, NaN, Infinity, "63.25", undefined]) {
      let prepared;
      assert.doesNotThrow(() => { prepared = api.goeduPrepareRate(field, invalid); });
      assert.equal(prepared.patch, null);
      assert.match(prepared.error, /숫자/);
      assert.deepEqual(before, { correct: [true, true, false], targetRate: 63.25, overrideRate: 63.25 });
    }
    for (const value of [0, 63.25, 100, ...(field === "overrideRate" ? [null] : [])]) {
      const prepared = api.goeduPrepareRate(field, value);
      assert.equal(prepared.error, null);
      const deferred = current => ({ ...current, ...prepared.patch });
      const current = { ...before, targetRate: 17.5, correct: [false, true, false] };
      let result;
      assert.doesNotThrow(() => { result = deferred(current); });
      assert.equal(result[field], value);
      assert.equal(result.correct, current.correct);
      if (field === "overrideRate") assert.equal(result.targetRate, 17.5);
    }
  }
  assert.ok(source.includes("if(i.error){window.alert(i.error);return}je(e,t,n,e=>({...e,...i.patch}))"));
  assert.ok(!source.includes("e=>goeduEditRate(e,"));
  assert.ok(source.includes("onChange:n=>Fe(A.id,p,e,n.target.valueAsNumber)"));
  assert.ok(source.includes("n.target.value===``?null:n.target.valueAsNumber"));
});

test("fractional points survive input, Yi, Ga and JSON roundtrip without total rounding", () => {
  assert.equal(api.Ri("7.125"), 7.125);
  assert.equal(api.Yi(1, undefined, { points: 7.125 }).points, 7.125);
  const input = project();
  input.items[0].points = 7.125;
  const original = JSON.stringify(input);
  assert.equal(api.Ga(input.items, input.judges)[0].points, 7.125);
  const loaded = api.goeduReadProject(JSON.parse(api.goeduSerializeProject(input)));
  assert.equal(loaded.items[0].points, 7.125);
  assert.equal(JSON.stringify(input), original);
  const average = (2 / 3 * 100 + 63.25) / 2;
  near(api.aa(loaded.items, loaded.judges).C, 7.125 * average / 100);
  near(api.oa(loaded.items, "judge-1").C, 4.75);
  const shared = require(process.env.GOEDUSPLIT_EXPECTED_RATES_MODULE || path.join(path.dirname(bundlePath), "../expected-rates.js"));
  const summary = shared.summarize(loaded);
  assert.equal(summary.total_points, 7.125);
  near(summary.raw_cuts.C, api.aa(loaded.items, loaded.judges).C);
  near(summary.scaled_cuts.C, average);
  assert.ok(source.includes("me=(0,l.useMemo)(()=>h.reduce((e,t)=>e+t.points,0),[h])"));
  assert.ok(source.includes("e[n].points=e[n].points+t.points"));
  assert.ok(source.includes("points-input`,type:`number`,min:`0`,step:`any`"));
});

test("an existing judgment map must contain all project judges and their A through E", () => {
  for (const corrupt of [
    p => delete p.items[0].judgmentsByJudge["judge-2"],
    p => { p.items[0].judgmentsByJudge = {}; },
    p => { p.items[0].judgmentsByJudge["judge-2"] = {}; },
    p => delete p.items[0].judgmentsByJudge["judge-2"].E,
    p => { p.items[0].judgmentsByJudge["judge-2"] = null; },
  ]) {
    const input = project();
    corrupt(input);
    freeze(input);
    let state = project();
    const before = state;
    assert.throws(() => { state = api.goeduReadProject(input); }, /판단|검토안/);
    assert.equal(state, before);
    assert.throws(() => api.Ga(input.items, input.judges));
    assert.throws(() => api.goeduSerializeProject(input));
  }
  const legacy = project();
  delete legacy.items[0].judgmentsByJudge;
  const loaded = api.goeduReadProject(legacy);
  for (const judge of loaded.judges) {
    for (const level of levels) assert.equal(loaded.items[0].judgmentsByJudge[judge.id][level].correct.length, 3);
  }
});
