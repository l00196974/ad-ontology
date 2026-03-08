#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');
const { generateChartOption } = require('../lib/chart-generator');

function readInput() {
  const inputFlagIndex = process.argv.indexOf('--input');
  if (inputFlagIndex !== -1) {
    const target = process.argv[inputFlagIndex + 1];
    if (!target) {
      throw new Error('--input requires a file path');
    }
    const filePath = path.resolve(process.cwd(), target);
    return fs.readFileSync(filePath, 'utf8');
  }

  if (process.stdin.isTTY) {
    throw new Error('input is required via stdin or --input');
  }

  return fs.readFileSync(0, 'utf8');
}

function outputError(message, code = 'INVALID_INPUT') {
  process.stderr.write(`${JSON.stringify({ error: { code, message } })}\n`);
  process.exit(1);
}

try {
  const raw = readInput();
  const payload = JSON.parse(raw);
  const result = generateChartOption(payload);
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
} catch (error) {
  outputError(error.message);
}
