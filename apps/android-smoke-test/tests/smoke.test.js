import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('smoke fixture has a web entry point', async () => {
  const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(html, /AppForge Android Smoke Test/);
});

test('smoke fixture declares the expected Capacitor app id', async () => {
  const config = JSON.parse(await readFile(new URL('../capacitor.config.json', import.meta.url), 'utf8'));
  assert.equal(config.appId, 'com.appforge.androidsmoketest');
  assert.equal(config.webDir, 'dist');
});
