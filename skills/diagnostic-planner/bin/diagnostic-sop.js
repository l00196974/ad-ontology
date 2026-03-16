#!/usr/bin/env node
'use strict';

const path = require('path');
const {
  formatError,
  formatSuccess,
  getScenarioArg,
  loadSops,
  matchScenario
} = require('../lib/sop-store');

function main() {
  const scenario = getScenarioArg(process.argv.slice(2));
  const csvPath = path.join(__dirname, '..', 'config', 'sop.csv');

  if (!scenario) {
    const error = formatError(
      'INVALID_ARGUMENT',
      'Missing required argument --scenario',
      scenario,
      []
    );
    process.stderr.write(`${JSON.stringify(error)}\n`);
    process.exitCode = 1;
    return;
  }

  try {
    const entries = loadSops(csvPath);
    const match = matchScenario(entries, scenario);

    if (!match) {
      const candidates = entries.map(e => e.scenario);
      process.stdout.write(JSON.stringify({
        ok: false,
        query: scenario,
        matched: false,
        message: `未找到匹配场景"${scenario}"的标准 SOP，请根据业务经验自行诊断。`,
        candidates,
      }, null, 2) + '\n');
      return;
    }

    process.stdout.write(`${JSON.stringify(formatSuccess(match, scenario), null, 2)}\n`);
  } catch (error) {
    const payload = formatError(
      'INTERNAL_ERROR',
      error && error.message ? error.message : 'Unknown error',
      scenario,
      []
    );
    process.stderr.write(`${JSON.stringify(payload)}\n`);
    process.exitCode = 1;
  }
}

main();
