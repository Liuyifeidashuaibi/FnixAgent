/** L4: AG-UI SSE ↔ Work NDJSON bridge */

function parseSseBlock(block) {
  const dataLines = block
    .split(/\r?\n/)
    .filter((l) => l.startsWith('data:'))
    .map((l) => l.slice(5).trim());
  if (!dataLines.length) return null;
  try {
    return JSON.parse(dataLines.join('\n'));
  } catch {
    return null;
  }
}

function agUiEventToWorkLine(event) {
  const type = String(event.type || '');
  if (!type || type === 'RUN_STARTED') return null;
  if (type === 'CUSTOM') {
    return JSON.stringify({
      type: event.name,
      chunk_type: event.name,
      content: event.value,
      done: false,
    });
  }
  if (type === 'RUN_FINISHED') {
    return JSON.stringify({ type: 'done', chunk_type: 'done', content: event.result, done: true });
  }
  if (type === 'RUN_ERROR') {
    return JSON.stringify({
      type: 'error',
      chunk_type: 'error',
      content: event.message,
      done: true,
    });
  }
  return null;
}

function consumeSseBuffer(buffer, onEvent) {
  const parts = buffer.split(/\n\n/);
  const rest = parts.pop() ?? '';
  for (const block of parts) {
    const ev = parseSseBlock(block);
    if (ev && typeof ev === 'object') onEvent(ev);
  }
  return rest;
}

const sample =
  'data: {"type":"RUN_STARTED","runId":"abc"}\n\n' +
  'data: {"type":"CUSTOM","name":"mission","value":{"title":"T1","intent":"x"}}\n\n' +
  'data: {"type":"RUN_FINISHED","result":{"result":"ok"}}\n\n';

const lines = [];
consumeSseBuffer(sample, (ev) => {
  const line = agUiEventToWorkLine(ev);
  if (line) lines.push(JSON.parse(line));
});

if (lines.length !== 2) throw new Error(`expected 2 lines, got ${lines.length}`);
if (lines[0].chunk_type !== 'mission') throw new Error('mission missing');
if (lines[1].chunk_type !== 'done') throw new Error('done missing');
console.log('[ok] ag-ui stream bridge checks passed');
