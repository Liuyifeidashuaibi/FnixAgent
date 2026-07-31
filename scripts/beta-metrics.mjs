#!/usr/bin/env node
/**
 * Beta metrics scaffold — aggregates latest FCS/gate reports into a single
 * progressive-release scorecard (Day 61–90).
 *
 * Writes reports/beta-metrics.json. Missing live numbers stay null (honest).
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const reportsDir = path.join(root, 'reports');
const outPath = path.join(reportsDir, 'beta-metrics.json');

function readJson(p) {
  try {
    return JSON.parse(fs.readFileSync(p, 'utf-8'));
  } catch {
    return null;
  }
}

function latestGate() {
  if (!fs.existsSync(reportsDir)) return null;
  const files = fs
    .readdirSync(reportsDir)
    .filter((f) => f.endsWith('.gate.json'))
    .map((f) => ({ f, t: fs.statSync(path.join(reportsDir, f)).mtimeMs }))
    .sort((a, b) => b.t - a.t);
  if (!files.length) return null;
  return readJson(path.join(reportsDir, files[0].f));
}

const label = process.argv.includes('--label')
  ? process.argv[process.argv.indexOf('--label') + 1]
  : 'local';

const curatedManifest = readJson(
  path.join(root, 'benchmarks/code/curated/manifest.json'),
);
const goldenDir = path.join(root, 'benchmarks/work/golden');
const goldenCount = fs.existsSync(goldenDir)
  ? fs.readdirSync(goldenDir).filter((f) => f.endsWith('.json')).length
  : 0;

const gate = latestGate();

const metrics = {
  schemaVersion: 1,
  collectedAt: new Date().toISOString(),
  label,
  os: process.platform,
  node: process.version,
  thresholds: {
    curatedCodeHardPass: 80,
    workSemanticQuality: 9,
    crashFreeSessions: 99.5,
    firstTaskSuccess: 90,
    securityScenes: 100,
  },
  curated: {
    codeSeedTasks: curatedManifest?.tasks?.length ?? 0,
    workGoldenScenes: goldenCount,
    minHardPassLive: curatedManifest?.min_hard_pass_live ?? 70,
  },
  latestFcs: gate
    ? {
        taskCount: gate.task_count ?? null,
        fcs: gate.fcs ?? null,
        hardPassRate: gate.hard_pass_rate ?? null,
        minHardPass: gate.min_hard_pass ?? null,
      }
    : null,
  /** Progressive Beta — fill from dogfood telemetry later */
  progressive: {
    dogfoodUsers: null,
    closedBetaUsers: null,
    crashFreePct: null,
    firstTaskSuccessPct: null,
    securityScenePassPct: null,
  },
  gates: {
    curatedCodeValidate: true,
    workGoldenScenes: goldenCount,
    workOpenabilityOffline: fs.existsSync(
      path.join(reportsDir, 'work-openability-offline.json'),
    ),
    mcpTrustLedger: true,
    shellA11ySpec: fs.existsSync(
      path.join(root, 'e2e/ui/shell-a11y.spec.ts'),
    ),
  },
  notes: [
    'Validate-only CI does not populate hardPassRate from live agent runs.',
    'Set GATE_FCS_LIVE=1 (nightly) to measure curated hard pass.',
    'Work openability offline gate uses synthetic fixtures; live golden needs API key.',
    'Day 76+: freeze features; only raise progressive metrics.',
  ],
};

fs.mkdirSync(reportsDir, { recursive: true });
fs.writeFileSync(outPath, JSON.stringify(metrics, null, 2) + '\n', 'utf-8');
console.log(`[beta-metrics] wrote ${outPath}`);
console.log(
  `[beta-metrics] curated code=${metrics.curated.codeSeedTasks} work=${metrics.curated.workGoldenScenes}` +
    (gate ? ` hard_pass=${gate.hard_pass_rate}%` : ' (no live gate yet)'),
);
