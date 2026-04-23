// Anno1800Calculator の js/params.js から populationLevels (tier 別消費レート)
// を安全に抽出して JSON を stdout に書き出す．
//
// ``params.js`` は ``if(window.params == null)window.params={...};`` の形で
// 大きな object literal を export する browser 向け script．JavaScript の
// object literal は厳密 JSON でない (trailing comma 等) ので ``json5`` で
// パースする．**eval / vm は使わない**．
//
// Usage::
//
//     node scripts/extract_calculator_data.mjs <calculator-dir>

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import JSON5 from 'json5';

const [, , calcDir] = process.argv;
if (!calcDir) {
  console.error('Usage: node extract_calculator_data.mjs <calculator-dir>');
  process.exit(2);
}

const paramsPath = path.join(calcDir, 'js', 'params.js');
if (!fs.existsSync(paramsPath)) {
  console.error(`params.js not found at ${paramsPath}`);
  process.exit(2);
}

const src = fs.readFileSync(paramsPath, 'utf-8');

// object literal を bracket balancing で抽出．
// 先頭の `window.params = ` (guard 節や var 宣言を含む) の直後の `{` から
// 対応する `}` までを切り出す．
function extractObjectLiteral(text) {
  // ``==`` (比較演算子) に誤マッチしないよう single ``=`` の直後を negative
  // lookahead で限定．``if(window.params == null)window.params={...}`` の
  // 2 個目の代入にヒットさせる．
  const assignRe = /window\.params\s*=(?!=)\s*/g;
  let i = -1;
  for (const m of text.matchAll(assignRe)) {
    const after = text[m.index + m[0].length];
    if (after === '{') {
      i = m.index + m[0].length;
      break;
    }
  }
  if (i < 0) {
    throw new Error('assignment to window.params with object literal not found');
  }
  let depth = 0;
  let inString = false;
  let stringQuote = '';
  let escape = false;
  for (let j = i; j < text.length; j += 1) {
    const ch = text[j];
    if (escape) {
      escape = false;
      continue;
    }
    if (inString) {
      if (ch === '\\') { escape = true; continue; }
      if (ch === stringQuote) { inString = false; }
      continue;
    }
    if (ch === '"' || ch === "'") { inString = true; stringQuote = ch; continue; }
    if (ch === '{') { depth += 1; continue; }
    if (ch === '}') {
      depth -= 1;
      if (depth === 0) { return text.slice(i, j + 1); }
    }
  }
  throw new Error('unbalanced braces in params.js');
}

const literal = extractObjectLiteral(src);
const params = JSON5.parse(literal);

if (!Array.isArray(params.populationLevels)) {
  console.error('params.populationLevels missing or not an array');
  process.exit(1);
}

const tiers = params.populationLevels.map((level) => ({
  guid: level.guid,
  name: level.name,
  loca_text: level.locaText || {},
  full_house: level.fullHouse ?? null,
  icon_path: level.iconPath ?? null,
  dlcs: level.dlcs ?? [],
  needs: (level.needs || []).map((n) => ({
    product_guid: n.guid,
    tpmin: n.tpmin ?? null,
    residents: n.residents ?? 0,
    happiness: n.happiness ?? 0,
    is_bonus_need: Boolean(n.isBonusNeed),
    dlcs: n.dlcs ?? [],
    unlock_condition: n.unlockCondition ?? null,
  })),
}));

const payload = {
  source: { calculator_version: params.version ?? null },
  tiers,
};

process.stdout.write(JSON.stringify(payload, null, 2) + '\n');
