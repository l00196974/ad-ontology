'use strict';

const test = require('node:test');
const assert = require('node:assert');
const path = require('path');
const { spawnSync } = require('child_process');
const { loadSops, matchScenario, normalizeText } = require('../lib/sop-store');

const skillDir = path.join(__dirname, '..');
const csvPath = path.join(skillDir, 'config', 'sop.csv');
const binPath = path.join(skillDir, 'bin', 'diagnostic-sop.js');

test('normalizeText removes spacing and punctuation', () => {
  assert.equal(normalizeText(' CPA 突然升高！ '), 'cpa突然升高');
});

test('matches exact scenario', () => {
  const entries = loadSops(csvPath);
  const match = matchScenario(entries, '线索成本突增');

  assert.ok(match);
  assert.equal(match.matchType, 'exact');
  assert.equal(match.entry.scenario, '线索成本突增');
});

test('matches alias scenario', () => {
  const entries = loadSops(csvPath);
  const match = matchScenario(entries, '最近获客成本突然变贵');

  assert.ok(match);
  assert.equal(match.matchType, 'alias');
  assert.equal(match.entry.scenario, '线索成本突增');
});

test('matches fuzzy scenario', () => {
  const entries = loadSops(csvPath);
  const match = matchScenario(entries, '高潜质人群画像');

  assert.ok(match);
  assert.equal(match.matchType, 'fuzzy');
  assert.equal(match.entry.scenario, '高潜人群画像分析');
});

test('cli prints success json to stdout', () => {
  const result = spawnSync(process.execPath, [binPath, '--scenario', '线索成本突增'], {
    encoding: 'utf8'
  });

  assert.equal(result.status, 0);
  assert.equal(result.stderr, '');

  const payload = JSON.parse(result.stdout);
  assert.equal(payload.ok, true);
  assert.equal(payload.matchType, 'exact');
  assert.ok(Array.isArray(payload.steps));
  assert.ok(payload.steps.length > 0);
});

test('cli prints structured error json to stderr', () => {
  const result = spawnSync(process.execPath, [binPath, '--scenario', '完全不存在的场景'], {
    encoding: 'utf8'
  });

  assert.notEqual(result.status, 0);
  assert.equal(result.stdout, '');

  const payload = JSON.parse(result.stderr);
  assert.equal(payload.ok, false);
  assert.equal(payload.error.code, 'SCENARIO_NOT_FOUND');
  assert.ok(Array.isArray(payload.error.candidates));
  assert.ok(payload.error.candidates.includes('线索成本突增'));
});
