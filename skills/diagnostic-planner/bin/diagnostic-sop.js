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
      const error = formatError(
        'SCENARIO_NOT_FOUND',
        `No diagnostic SOP found for scenario: ${scenario}`,
        scenario,
        entries
      );
      process.stderr.write(`${JSON.stringify(error)}\n`);
      process.exitCode = 1;
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
