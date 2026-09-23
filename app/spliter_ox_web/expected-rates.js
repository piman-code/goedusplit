(function (root) {
  "use strict";
  const LEVELS = ["A", "B", "C", "D", "E"];
  const types = {"선택형": 0, "서답형": 1};
  const diffs = {"쉬움": 0, "보통": 1, "어려움": 2};
  function number(value, label) {
    if (value == null || value === "" || typeof value === "boolean" || !Number.isFinite(Number(value))) throw new Error(`${label}: 숫자를 입력해 주세요.`);
    return Number(value);
  }
  function cellRate(cell) {
    if (!cell || typeof cell !== "object") throw new Error("A~E 예상정답률을 모두 입력해 주세요.");
    let value;
    if (cell.overrideRate != null && cell.overrideRate !== "") value = number(cell.overrideRate, "직접 정답률");
    else if (Array.isArray(cell.correct) && cell.correct.length) {
      if (cell.correct.some(v => typeof v !== "boolean")) throw new Error("O/X 입력 형식을 확인해 주세요.");
      value = cell.correct.filter(Boolean).length / cell.correct.length * 100;
    } else value = number(cell.targetRate, "예상정답률");
    if (value < 0 || value > 100) throw new Error("예상정답률은 0~100%로 입력해 주세요.");
    return value;
  }
  function designsFromProject(project) {
    if (!project || !Array.isArray(project.items)) throw new Error("문항 정보를 확인해 주세요.");
    const ids = (Array.isArray(project.judges) ? project.judges : []).map(j => j.id);
    if (new Set(ids).size !== ids.length) throw new Error("검토안 ID가 중복되었습니다.");
    return project.items.map((item, index) => {
      const judged = item.judgmentsByJudge || {}, active = ids.length ? ids : Object.keys(judged);
      if (!active.length) throw new Error(`${index + 1}행 검토안이 없습니다.`);
      const rates = {};
      LEVELS.forEach(level => { rates[level] = active.reduce((sum, id) => sum + cellRate(judged[id]?.[level]), 0) / active.length; });
      return {number: item.number, type: /서답|논술|주관|단답|서술|구성/.test(item.type || "") ? "서답형" : "선택형", points: item.points,
        difficulty: item.difficulty, target: item.targetLevel, rates, standard: item.standard || ""};
    });
  }
  function validate(designs) {
    if (!Array.isArray(designs) || designs.length > 1000) throw new Error("문항 목록은 1,000개 이내여야 합니다.");
    const seen = new Set();
    designs.forEach((item, index) => {
      const n = number(item.number, `${index + 1}행 문항번호`);
      if (!Number.isInteger(n) || n <= 0) throw new Error(`${index + 1}행 문항번호는 양의 정수여야 합니다.`);
      if (!Object.hasOwn(types, item.type) || !Object.hasOwn(diffs, item.difficulty)) throw new Error(`${index + 1}행 문항구분과 난이도를 확인해 주세요.`);
      const key = `${item.type}:${n}`;
      if (seen.has(key)) throw new Error(`${item.type} ${n}번이 중복되었습니다.`);
      seen.add(key);
      const points = number(item.points, `${index + 1}행 배점`);
      if (!(points > 0 && points <= 10000)) throw new Error(`${index + 1}행 배점은 0보다 크고 10,000점 이하여야 합니다.`);
      LEVELS.forEach((level, i) => {
        const rate = number(item.rates?.[level], `${level} 예상정답률`);
        if (rate < 0 || rate > 100) throw new Error("예상정답률은 0~100%로 입력해 주세요.");
        if (i && rate > item.rates[LEVELS[i - 1]]) throw new Error(`${item.type} ${n}번: A~E 예상정답률의 역전을 확인해 주세요.`);
      });
    });
  }
  function roundRate(value) {
    const n = number(value, "NEIS 예상정답률");
    if (n < 0 || n > 100) throw new Error("NEIS 예상정답률은 0~100%여야 합니다.");
    return Math.min(100, 5 * Math.floor(n / 5 + 0.5 + 1e-12));
  }
  function rowsFromDesigns(designs) {
    validate(designs);
    const groups = new Map();
    designs.forEach(item => {
      const key = `${item.type}:${item.difficulty}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
    });
    return [...groups.values()].sort((a, b) => types[a[0].type] - types[b[0].type] || diffs[a[0].difficulty] - diffs[b[0].difficulty]).map(items => {
      items.sort((a, b) => a.number - b.number);
      const points = items.reduce((sum, item) => sum + Number(item.points), 0);
      const row = {"문항구분": items[0].type, "난이도": items[0].difficulty, "해당문항번호": items.map(i => i.number).join(", "),
        "문항수": items.length, "배점합": points, "목표수준": items.map(i => `${i.number}:${i.target || ""}`).join(", ")};
      LEVELS.forEach(level => { row[level] = roundRate(items.reduce((sum, i) => sum + Number(i.points) * i.rates[level], 0) / points); });
      return row;
    });
  }
  function summarizeDesigns(designs) {
    const rows = rowsFromDesigns(designs), total = designs.reduce((sum, item) => sum + Number(item.points), 0);
    const result = {item_count: designs.length, total_points: total, raw_cuts: {}, scaled_cuts: {}, neis_raw_cuts: {}, neis_scaled_cuts: {}};
    LEVELS.forEach(level => {
      result.raw_cuts[level] = designs.reduce((sum, item) => sum + Number(item.points) * item.rates[level] / 100, 0);
      result.neis_raw_cuts[level] = rows.reduce((sum, row) => sum + row["배점합"] * row[level] / 100, 0);
      result.scaled_cuts[level] = total ? result.raw_cuts[level] / total * 100 : 0;
      result.neis_scaled_cuts[level] = total ? result.neis_raw_cuts[level] / total * 100 : 0;
    });
    return result;
  }
  const api = {LEVELS, cellRate, designsFromProject, validate, roundRate, rowsFromDesigns, summarizeDesigns,
    summarize: project => summarizeDesigns(designsFromProject(project))};
  root.GoeduExpectedRates = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(globalThis);
