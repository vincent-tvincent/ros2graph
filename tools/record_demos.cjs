#!/usr/bin/env node
/* Record the actual viewer against the live, hardware-free demo.
 * Requires Playwright (development only), Chrome/Chromium and FFmpeg.
 * No fixtures, generated message counts or changes to application assets.
 */
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {parseArgs} = require('node:util');
const {spawnSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const {values} = parseArgs({options: {
  url: {type: 'string', default: 'http://127.0.0.1:8080'},
  out: {type: 'string', default: path.join(os.tmpdir(), 'ros2graph-recordings')},
  only: {type: 'string'},
  chrome: {type: 'string'},
  fps: {type: 'string', default: '10'},
}});
const fps = Number(values.fps);
if (!Number.isInteger(fps) || fps < 5 || fps > 20) throw Error('--fps must be 5..20');
const output = path.resolve(values.out);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const object = id => `[data-object-id="${id}"]`;
const topic = object('topic:/ros2graph_demo/chatter');
const service = object('service:/ros2graph_demo/trigger');
const action = object('action:/ros2graph_demo/fibonacci');
const server = object('node:/ros2graph_demo/server');

async function installRecordingOverlay(page, label) {
  await page.evaluate(label => {
    const style = document.createElement('style');
    style.textContent = `
      #recording-caption { position:fixed; top:24px; left:30%; width:44%; max-width:640px;
        box-sizing:border-box; background:#191919; color:white; border-left:4px solid #2359ba;
        padding:9px 15px 11px; z-index:10000; pointer-events:none; font-family:Helvetica,Arial,sans-serif; }
      #recording-caption small { display:block; color:#c8c8c5; font-size:10px; font-weight:700;
        letter-spacing:1px; margin-bottom:5px; }
      #recording-caption strong { display:block; font-size:17px; font-weight:500; line-height:1.2; }
      #recording-cursor { position:fixed; left:0; top:0; width:23px; height:29px;
        pointer-events:none; z-index:10002; transform:translate(715px,110px); }
      #recording-click { position:fixed; width:28px; height:28px; border:2px solid #2359ba;
        border-radius:50%; transform:translate(-50%,-50%); z-index:10001; pointer-events:none;
        opacity:0; transition:opacity 180ms; }
    `;
    document.head.append(style);
    const caption = document.createElement('div'); caption.id = 'recording-caption';
    const category = document.createElement('small'); category.textContent = label;
    const text = document.createElement('strong'); text.textContent = 'Live ROS 2 demo';
    caption.append(category, text); document.body.append(caption);
    const cursor = document.createElement('div'); cursor.id = 'recording-cursor';
    cursor.innerHTML = '<svg viewBox="0 0 23 29"><path d="M2 1v22l5-5 5 10 4-2-5-9h8Z" fill="#191919" stroke="white" stroke-width="1.5"/></svg>';
    document.body.append(cursor);
    const click = document.createElement('div'); click.id = 'recording-click'; document.body.append(click);
    document.addEventListener('pointermove', event => {
      cursor.style.transform = `translate(${event.clientX}px,${event.clientY}px)`;
    });
    document.addEventListener('pointerdown', event => {
      click.style.left = event.clientX + 'px'; click.style.top = event.clientY + 'px'; click.style.opacity = '1';
      setTimeout(() => {click.style.opacity = '0';}, 260);
    });
  }, label);
}

async function caption(page, text) {
  await page.locator('#recording-caption strong').evaluate((element, text) => {element.textContent = text;}, text);
}
async function hover(page, selector) {
  const box = await page.locator(selector).first().boundingBox();
  if (!box) throw Error('Not visible: ' + selector);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, {steps: 12});
  await sleep(220);
}
async function click(page, selector, pause = 1400) {
  await hover(page, selector); await page.locator(selector).first().click(); await sleep(pause);
}
async function choose(page, value, pause = 1600) {
  await hover(page, '#graph-update-interval');
  await page.locator('#graph-update-interval').selectOption(value); await sleep(pause);
}
async function type(page, selector, text) {
  await click(page, selector, 150);
  await page.locator(selector).fill('');
  await page.locator(selector).pressSequentially(text, {delay: 70});
  await sleep(1300);
}
async function inspectorScroll(page, amount) {
  const box = await page.locator('#graph-inspector').boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + 100, {steps: 10});
  for (let i = 0; i < 5; i++) {await page.mouse.wheel(0, amount / 5); await sleep(130);}
  await sleep(1300);
}
async function snapshot(page) {
  const response = await page.request.get(values.url + '/api/graph');
  if (!response.ok()) throw Error('Graph API: ' + response.status());
  const graph = await response.json();
  const row = (kind, name) => graph[kind].find(value => value.name === '/ros2graph_demo/' + name);
  return {topology_sequence: graph.sequence, watch_active: graph.watch.active,
    topic: row('topics', 'chatter').activity,
    service: row('services', 'trigger').activity,
    action: row('actions', 'fibonacci').activity,
    trace_state: graph.rpc_trace.state};
}

const scenes = [
  {
    name: '01-live-traffic', label: '01 / LIVE TRAFFIC',
    async run(page) {
      await caption(page, 'Real messages drive the dots and counters');
      await click(page, topic, 2600);
      await caption(page, 'Choose a faster display update: 0.5 seconds');
      await choose(page, '500', 3000);
      await caption(page, 'Pause this view’s live monitoring');
      await click(page, '#graph-live-flow', 2000);
      await caption(page, 'Resume live monitoring');
      await click(page, '#graph-live-flow', 3600);
      await caption(page, 'Dot labels count messages in the update interval');
      await choose(page, '1000', 2000);
      await click(page, '#refresh-graph', 600);
      await caption(page, 'Clear selection: monitoring continues without markers');
      await click(page, '#graph-clear', 1300);
    },
  },
  {
    name: '02-explore-focus', label: '02 / EXPLORE & FOCUS',
    async run(page) {
      await caption(page, 'Select a topic to highlight both sides');
      await click(page, topic, 2000);
      await caption(page, 'Follow a binding to its ROS node');
      await click(page, '#graph-inspector .binding button:text-is("/ros2graph_demo/server")', 1800);
      await caption(page, 'Double-click to isolate a topic and its neighbors');
      await hover(page, topic); await page.locator(topic).dblclick(); await sleep(2200);
      if (!await page.locator('#graph-exit').isVisible()) throw Error('Focus did not open');
      await caption(page, 'Zoom in, then pan the focused graph');
      await click(page, '#graph-zoom-in', 300);
      await click(page, '#graph-zoom-in', 700);
      const box = await page.locator('#graph-canvas').boundingBox();
      await page.mouse.move(box.x + 120, box.y + 70, {steps: 12});
      await page.mouse.down(); await page.mouse.move(box.x + 230, box.y + 115, {steps: 22});
      await page.mouse.up(); await sleep(1300);
      await caption(page, 'Fit the graph and return to the overview');
      await click(page, '#graph-fit', 1300);
      await click(page, '#graph-exit', 1800);
      await click(page, '#graph-clear', 900);
    },
  },
  {
    name: '03-filter-search', label: '03 / FILTER & SEARCH',
    async run(page) {
      await caption(page, 'Choose which interface types appear');
      await click(page, '#graph-show-services', 900);
      await click(page, '#graph-show-actions', 1500);
      await click(page, '#graph-show-topics', 1300);
      await caption(page, 'The list can reveal interfaces hidden in the diagram');
      await click(page, '[data-interface="services"]', 250);
      await click(page, 'button.interface-row:has([data-interface-rate="service:/ros2graph_demo/trigger"])', 750);
      await click(page, '[data-interface="actions"]', 250);
      await click(page, 'button.interface-row:has([data-interface-rate="action:/ros2graph_demo/fibonacci"])', 750);
      await click(page, '[data-interface="topics"]', 250);
      await click(page, 'button.interface-row:has([data-interface-rate="topic:/ros2graph_demo/chatter"])', 750);
      await caption(page, 'Inspect infrastructure when you need the full graph');
      await click(page, '#show-infrastructure', 1900);
      await caption(page, 'Search names and interface types');
      await type(page, '#graph-search', 'trigger');
      await sleep(1100);
      await caption(page, 'Clear the search and restore the overview');
      await page.locator('#graph-search').fill(''); await sleep(800);
      await click(page, '#show-infrastructure', 1500);
    },
  },
  {
    name: '04-services-actions', label: '04 / SERVICES & ACTIONS',
    async run(page) {
      await caption(page, 'Services expose measured request and reply activity');
      await click(page, '[data-interface="services"]', 400);
      await click(page, 'button.interface-row:has([data-interface-rate="service:/ros2graph_demo/trigger"])', 2200);
      await caption(page, 'Inspect sent and received phases separately');
      await inspectorScroll(page, 350); await sleep(1600);
      await caption(page, 'Actions add feedback, status, goal, cancel and result');
      await click(page, '[data-interface="actions"]', 400);
      await click(page, 'button.interface-row:has([data-interface-rate="action:/ros2graph_demo/fibonacci"])', 2500);
      await page.locator('#graph-inspector').evaluate(element => {element.scrollTop = 0;});
      await sleep(1000);
      await caption(page, 'Watch action status and feedback update live');
      await inspectorScroll(page, 210); await sleep(2000);
      await caption(page, 'Inspect goal, cancellation and result RPC channels');
      await inspectorScroll(page, 370); await sleep(2200);
    },
  },
  {
    name: '05-layout-notes', label: '05 / LAYOUT & NOTES',
    async run(page) {
      await caption(page, 'Pause this view while arranging the layout');
      await click(page, '#graph-live-flow', 800);
      await caption(page, 'Infrastructure reveals the full interface list');
      await click(page, '[data-interface="services"]', 200);
      await click(page, '#show-infrastructure', 800);
      await caption(page, 'Drag the divider to give the interface list more space');
      const originalHeight = Number(await page.locator('#graph-interface-resizer').getAttribute('aria-valuenow'));
      const box = await page.locator('#graph-interface-resizer').boundingBox();
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, {steps: 12});
      await page.mouse.down(); await page.mouse.move(box.x + box.width / 2, box.y - 90, {steps: 22});
      await page.mouse.up(); await sleep(1800);
      if (Number(await page.locator('#graph-interface-resizer').getAttribute('aria-valuenow')) <= originalHeight)
        throw Error('Interface pane did not expand');
      await caption(page, 'Scroll the list independently of the diagram');
      await hover(page, '#interface-list'); await page.mouse.wheel(0, 340); await sleep(1500);
      await click(page, '#show-infrastructure', 500);
      await click(page, '[data-interface="topics"]', 700);
      await caption(page, 'Select a node and add a note local to this view');
      await click(page, server, 1000);
      await page.locator('.graph-annotation').scrollIntoViewIfNeeded();
      await type(page, '.graph-annotation', 'Demo publisher / 10 Hz');
      await page.locator('#graph-canvas').click({position: {x: 80, y: 50}});
      await sleep(2000);
      await caption(page, 'Keyboard resizing: Home restores the default height');
      await click(page, '#graph-interface-resizer', 200);
      await page.keyboard.press('Home'); await sleep(1500);
      if (Number(await page.locator('#graph-interface-resizer').getAttribute('aria-valuenow')) !== originalHeight)
        throw Error('Interface pane did not reset');
      await click(page, '#graph-fit', 1500);
      await caption(page, 'Resume monitoring; the node keeps its local note');
      await click(page, topic, 300);
      await click(page, '#graph-live-flow', 2600);
    },
  },
];

async function capture(page, directory, run) {
  await fs.mkdir(directory, {recursive: true});
  const frames = []; let done = false; let failure;
  const began = performance.now();
  const actions = run().catch(error => {failure = error;}).finally(() => {done = true;});
  while (!done || !frames.length) {
    const tick = performance.now();
    const file = path.join(directory, `${String(frames.length).padStart(5, '0')}.png`);
    await page.screenshot({path: file, animations: 'allow'});
    frames.push({file, at: (tick - began) / 1000});
    await sleep(Math.max(0, 1000 / fps - (performance.now() - tick)));
  }
  await actions;
  if (failure) throw failure;
  const duration = (performance.now() - began) / 1000;
  const quote = name => name.replaceAll("'", "'\\''");
  const lines = ['ffconcat version 1.0'];
  frames.forEach((frame, index) => {
    lines.push(`file '${quote(frame.file)}'`, `duration ${(frames[index + 1]?.at ?? duration) - frame.at}`);
  });
  lines.push(`file '${quote(frames.at(-1).file)}'`);
  const concat = path.join(directory, 'frames.ffconcat');
  await fs.writeFile(concat, lines.join('\n') + '\n');
  return {concat, duration, frame_count: frames.length};
}

function encode(concat, file) {
  // Two passes avoid retaining a whole uncompressed clip in a split-filter queue.
  const palette = path.join(path.dirname(concat), 'palette.png');
  const scale = `fps=${fps},scale=1280:-1:flags=lanczos`;
  const common = ['-hide_banner', '-loglevel', 'error', '-y', '-threads', '4', '-safe', '0', '-i', concat];
  for (const args of [
    [...common, '-vf', scale + ',palettegen=max_colors=128:stats_mode=diff', '-frames:v', '1', palette],
    [...common, '-i', palette, '-filter_complex',
      `[0:v]${scale}[v];[v][1:v]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle`, '-loop', '0', file],
  ]) {
    const result = spawnSync('ffmpeg', args, {encoding: 'utf8'});
    if (result.status !== 0) throw Error(result.stderr || 'FFmpeg failed');
  }
}

(async () => {
  await fs.mkdir(output, {recursive: true});
  const browser = await chromium.launch({headless: true, ...(values.chrome ? {executablePath: values.chrome} : {})});
  const manifest = {recorded_at: new Date().toISOString(), source: 'live ROS demo over HTTP',
    overlays: 'caption and cursor only; application assets and measurements unchanged',
    viewport: {width: 1440, height: 1000}, fps, clips: []};
  try {
    for (const scene of scenes.filter(scene => !values.only || values.only.split(',').includes(scene.name))) {
      console.log('Recording ' + scene.name);
      const context = await browser.newContext({viewport: manifest.viewport, deviceScaleFactor: 1, reducedMotion: 'no-preference'});
      const page = await context.newPage(); const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      try {
        await page.goto(values.url);
        await page.waitForSelector(topic);
        await page.waitForFunction(async () => {
          const graph = await fetch('/api/graph').then(response => response.json());
          const topic = graph.topics.find(row => row.name === '/ros2graph_demo/chatter');
          const service = graph.services.find(row => row.name === '/ros2graph_demo/trigger');
          const action = graph.actions.find(row => row.name === '/ros2graph_demo/fibonacci');
          const phases = ['request_sent', 'request_received', 'response_sent', 'response_received'];
          const measured = value => phases.every(phase => (value?.channels?.[phase]?.messages || 0) > 0);
          return topic?.activity?.state === 'watching' && measured(service?.activity) &&
            ['goal', 'cancel', 'result'].every(operation => measured(action?.activity?.rpc?.[operation]));
        }, undefined, {timeout: 30000, polling: 500});
        await page.locator('#graph-update-interval').selectOption('1000');
        await page.locator('#graph-fit').click();
        await sleep(2300);
        await installRecordingOverlay(page, scene.label);
        const before = await snapshot(page);
        const recording = await capture(page, path.join(output, scene.name), () => scene.run(page));
        const after = await snapshot(page);
        if (errors.length) throw Error(errors.join('\n'));
        const gif = path.join(output, scene.name + '.gif');
        encode(recording.concat, gif);
        manifest.clips.push({name: scene.name, duration_s: recording.duration,
          frames: recording.frame_count, bytes: (await fs.stat(gif)).size,
          errors, before, after});
        await fs.writeFile(path.join(output, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
        console.log(`Saved ${scene.name}: ${recording.duration.toFixed(1)} s, ${(await fs.stat(gif)).size} bytes`);
      } finally {await context.close();}
    }
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
