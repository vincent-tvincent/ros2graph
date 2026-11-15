import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const web=new URL('../ros2graph/web/',import.meta.url);
const source=name=>readFile(new URL(name,web),'utf8');

test('standalone document supplies every static graph/app DOM hook once',async()=>{
  const html=await source('index.html'),ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);
  assert.equal(ids.length,new Set(ids).size);
  for(const file of ['graph.js','app.js']) {
    const script=await source(file),references=[...script.matchAll(/\$\(["']([\w-]+)["']\)/g)].map(match=>match[1]);
    for(const id of references)assert.ok(ids.includes(id),`${file}: ${id}`);
  }
  for(const kind of ['topics','actions','services'])assert.ok(ids.includes('graph-show-'+kind));
  for(const id of ['operations','policies','camera-stage','arm-select','enable-control'])assert.equal(ids.includes(id),false);
  assert.match(html,/<title>ros2graph<\/title>/);assert.match(html,/<h1>ros2graph<\/h1>/);
  assert.match(html,/id="access-token" type="password" autocomplete="off"/);
});

test('public frontend assets and modules are self-contained and use only standalone graph API routes',async()=>{
  const html=await source('index.html');
  for(const match of html.matchAll(/(?:href|src)="\/assets\/([^"]+)"/g))assert.ok((await source(match[1])).length);
  for(const file of ['graph.js','app.js','client.js']) {
    const script=await source(file);
    for(const match of script.matchAll(/from ['"]\.\/([^'"]+)['"]/g))assert.ok((await source(match[1])).length);
    assert.doesNotMatch(script,/soarm_station|\/api\/v1\/ros\/|\.\/transport\.js|\.\/policy-management\.js|\.\/camera-layout\.js/);
  }
  assert.doesNotMatch(await source('styles.css'),/\.camera-stage|\.operation-panel|#policy-manager/);
});
