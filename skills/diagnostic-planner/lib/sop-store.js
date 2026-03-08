'use strict';

const fs = require('fs');
const path = require('path');

function parseCsvLine(line) {
  const fields = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];

    if (char === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === ',' && !inQuotes) {
      fields.push(current);
      current = '';
      continue;
    }

    current += char;
  }

  fields.push(current);
  return fields;
}

function parseCsv(content) {
  const lines = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length < 2) {
    return [];
  }

  const headers = parseCsvLine(lines[0]);
  return lines.slice(1).map((line) => {
    const values = parseCsvLine(line);
    const record = {};

    headers.forEach((header, index) => {
      record[header] = values[index] || '';
    });

    return {
      scenario: record.scenario,
      aliases: record.aliases
        .split('|')
        .map((item) => item.trim())
        .filter(Boolean),
      sop: record.sop.replace(/\\n/g, '\n').trim()
    };
  });
}

function normalizeText(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[()（）\-_—,，。！？!?:：;'"“”‘’/\\]/g, '');
}

function levenshtein(a, b) {
  const rows = a.length + 1;
  const cols = b.length + 1;
  const dp = Array.from({ length: rows }, () => new Array(cols).fill(0));

  for (let i = 0; i < rows; i += 1) {
    dp[i][0] = i;
  }

  for (let j = 0; j < cols; j += 1) {
    dp[0][j] = j;
  }

  for (let i = 1; i < rows; i += 1) {
    for (let j = 1; j < cols; j += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,
        dp[i][j - 1] + 1,
        dp[i - 1][j - 1] + cost
      );
    }
  }

  return dp[a.length][b.length];
}

function similarity(a, b) {
  if (!a || !b) {
    return 0;
  }

  if (a === b) {
    return 1;
  }

  if (a.includes(b) || b.includes(a)) {
    return Math.min(a.length, b.length) / Math.max(a.length, b.length);
  }

  const distance = levenshtein(a, b);
  return 1 - distance / Math.max(a.length, b.length);
}

function loadSops(csvPath) {
  const raw = fs.readFileSync(csvPath, 'utf8');
  return parseCsv(raw).map((entry) => ({
    ...entry,
    normalizedScenario: normalizeText(entry.scenario),
    normalizedAliases: entry.aliases.map(normalizeText)
  }));
}

function matchScenario(entries, input) {
  const normalizedInput = normalizeText(input);
  if (!normalizedInput) {
    return null;
  }

  for (const entry of entries) {
    if (entry.normalizedScenario === normalizedInput) {
      return { entry, matchType: 'exact', score: 1, matchedText: entry.scenario };
    }
  }

  for (const entry of entries) {
    const aliasIndex = entry.normalizedAliases.findIndex((alias) => alias === normalizedInput);
    if (aliasIndex >= 0) {
      return {
        entry,
        matchType: 'alias',
        score: 1,
        matchedText: entry.aliases[aliasIndex]
      };
    }
  }

  let best = null;
  for (const entry of entries) {
    const candidates = [entry.scenario, ...entry.aliases];
    for (const candidate of candidates) {
      const normalizedCandidate = normalizeText(candidate);
      const score = similarity(normalizedInput, normalizedCandidate);
      if (!best || score > best.score) {
        best = {
          entry,
          matchType: 'fuzzy',
          score,
          matchedText: candidate
        };
      }
    }
  }

  if (best && best.score >= 0.45) {
    return best;
  }

  return null;
}

function formatSuccess(match, query) {
  return {
    ok: true,
    query,
    scenario: match.entry.scenario,
    matchType: match.matchType,
    matchedText: match.matchedText,
    score: Number(match.score.toFixed(4)),
    aliases: match.entry.aliases,
    steps: match.entry.sop.split('\n').map((step) => step.trim()).filter(Boolean),
    raw: match.entry.sop
  };
}

function formatError(code, message, query, entries) {
  return {
    ok: false,
    error: {
      code,
      message,
      query,
      candidates: entries.map((entry) => entry.scenario)
    }
  };
}

function getScenarioArg(argv) {
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--scenario') {
      return argv[i + 1] || '';
    }
  }
  return '';
}

module.exports = {
  formatError,
  formatSuccess,
  getScenarioArg,
  loadSops,
  matchScenario,
  normalizeText,
  parseCsv,
  parseCsvLine,
  similarity
};
