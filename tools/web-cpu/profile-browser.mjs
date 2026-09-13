// GPL-2.0-or-later. Built-in Node APIs only; owns a separate Chrome profile.
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { createHash } from 'node:crypto';

const options = { seconds: 15, warmup: 0, chrome: process.env.CHROME_PATH ||
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    out: `tmp/web-cpu/browser-${new Date().toISOString().replaceAll(':', '-')}` };
for (let i = 2; i < process.argv.length; i++) {
    const arg = process.argv[i];
    if (arg === '--tests') options.tests = true;
    else if (arg === '--no-profile') options.noProfile = true;
    else if (arg === '--headless') options.headless = true;
    else if (['--url', '--out', '--chrome', '--seconds', '--warmup', '--manifest', '--stop-on'].includes(arg)) {
        const value = process.argv[++i];
        if (!value) throw new Error(`Missing ${arg} value`);
        options[arg.slice(2)] = ['--seconds', '--warmup'].includes(arg) ? Number(value) : value;
    } else throw new Error(`Unknown argument: ${arg}`);
}
if (!options.url || !/^https?:$/.test(new URL(options.url).protocol))
    throw new Error('Supply --url http://127.0.0.1:8093/tools/web-cpu/harness.html');
if (![options.seconds, options.warmup].every(Number.isFinite) ||
        options.seconds <= 0 || options.seconds > 300 || options.warmup < 0 || options.warmup > 300)
    throw new Error('Use seconds in (0, 300] and warmup in [0, 300]');
if (options.tests && options['stop-on']) throw new Error('Use either --tests or --stop-on');
if (options.noProfile && options.warmup) throw new Error('--no-profile measures from navigation; omit --warmup');
const stopPattern = options['stop-on'] ? new RegExp(options['stop-on']) : null;
const out = resolve(options.out);
await mkdir(out, { recursive: false }); // Never overwrite a previous capture.
const profileDir = await mkdtemp(join(tmpdir(), 'boxedwine-cpu-chrome-'));
const chrome = spawn(options.chrome, ['--remote-debugging-port=0',
    `--user-data-dir=${profileDir}`, '--no-first-run', '--no-default-browser-check',
    '--disable-extensions', '--disable-component-extensions-with-background-pages',
    ...(options.headless ? ['--headless=new'] : []), 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
const chromeLog = [];
chrome.stderr.on('data', chunk => chromeLog.push(String(chunk)));
let launchError;
chrome.on('error', error => { launchError = error; });
let socket;
let nextId = 0;
const pending = new Map();
const sessions = new Map();
const events = [];
const failures = [];
const setupTasks = new Set();
const captured = [];
let phase = 'setup';
let completion;
let navigationStartedAt;
let resolveCompletion;
const completed = new Promise(resolvePromise => { resolveCompletion = resolvePromise; });
const cancelled = new AbortController();
process.once('SIGINT', () => cancelled.abort());
process.once('SIGTERM', () => cancelled.abort());

function send(method, params = {}, sessionId) {
    return new Promise((resolvePromise, reject) => {
        const id = ++nextId;
        const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 30000);
        pending.set(id, { resolve: resolvePromise, reject, timer });
        socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
}
async function start(session) {
    if (options.noProfile) return;
    await send('Profiler.start', {}, session.id);
    session.startedAt = Date.now();
    session.recording = true;
}
async function stop(session) {
    if (!session.recording) return;
    session.recording = false;
    const { profile } = await send('Profiler.stop', {}, session.id);
    const name = `${session.type}-${session.number}.cpuprofile`;
    await writeFile(join(out, name), JSON.stringify(profile));
    captured.push({ file: name, type: session.type, url: session.url,
        startedAt: session.startedAt, stoppedAt: Date.now(), samples: profile.samples?.length ?? 0 });
}
async function attached(params) {
    const { sessionId, targetInfo } = params;
    if (!['page', 'worker'].includes(targetInfo.type) || targetInfo.url.startsWith('chrome-extension:')) {
        await send('Runtime.runIfWaitingForDebugger', {}, sessionId).catch(() => {});
        return;
    }
    const session = { id: sessionId, number: sessions.size, type: targetInfo.type, url: targetInfo.url };
    sessions.set(sessionId, session);
    try {
        // Recursive attachment catches Emscripten pthread and nested workers.
        await send('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: true, flatten: true }, sessionId);
        if (['page', 'worker'].includes(session.type)) {
            await send('Runtime.enable', {}, sessionId);
            if (!options.noProfile) {
                await send('Profiler.enable', {}, sessionId);
                await send('Profiler.setSamplingInterval', { interval: 1000 }, sessionId);
            }
            session.ready = true;
            if (phase === 'recording') await start(session);
        }
    } catch (error) { failures.push(`Attach ${session.type}: ${error.message}`); }
    finally { await send('Runtime.runIfWaitingForDebugger', {}, sessionId).catch(error => failures.push(error.message)); }
}

try {
    let portFile;
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
        cancelled.signal.throwIfAborted();
        if (launchError) throw launchError;
        if (chrome.exitCode !== null) throw new Error(`Chrome exited: ${chrome.exitCode}`);
        try { portFile = await readFile(join(profileDir, 'DevToolsActivePort'), 'utf8'); break; }
        catch { await delay(100); }
    }
    if (!portFile) throw new Error('Chrome did not expose a debugging port');
    const [port, path] = portFile.trim().split('\n');
    socket = new WebSocket(`ws://127.0.0.1:${port}${path}`);
    await new Promise((resolvePromise, reject) => {
        socket.addEventListener('open', resolvePromise, { once: true });
        socket.addEventListener('error', reject, { once: true });
    });
    socket.addEventListener('message', ({ data }) => {
        const message = JSON.parse(data);
        if (message.id) {
            const item = pending.get(message.id);
            if (!item) return;
            clearTimeout(item.timer);
            pending.delete(message.id);
            if (message.error) item.reject(new Error(message.error.message));
            else item.resolve(message.result);
        } else if (message.method === 'Target.attachedToTarget') {
            const task = attached(message.params);
            setupTasks.add(task);
            task.finally(() => setupTasks.delete(task));
        } else if (message.method === 'Target.detachedFromTarget') {
            const session = sessions.get(message.params.sessionId);
            if (session?.recording) failures.push(`Lost active ${session.type} profile on detach`);
            if (session) session.detached = true;
        } else if (message.method === 'Runtime.consoleAPICalled') {
            const text = message.params.args.map(arg => arg.value ?? arg.description ?? '').join(' ');
            const at = Date.now();
            events.push({ session: message.sessionId, type: message.params.type, text, at,
                elapsedMs: navigationStartedAt === undefined ? null : at - navigationStartedAt });
            const match = text.match(/^(\d+) tests FAILED in (\d+)s$/);
            if (options.tests && match) { completion = { failed: Number(match[1]), seconds: Number(match[2]) }; resolveCompletion(); }
            if (stopPattern && navigationStartedAt !== undefined && !completion && stopPattern.test(text)) {
                completion = { milestone: options['stop-on'], text, elapsedMs: at - navigationStartedAt };
                resolveCompletion();
            }
            if (text.startsWith('BOXEDWINE_ABORT:')) failures.push(text);
            if (text.includes('worker sent an unknown command')) failures.push(text);
        } else if (message.method === 'Runtime.exceptionThrown') {
            failures.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
        }
    });
    const version = await send('Browser.getVersion');
    await send('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: true, flatten: true });
    while (setupTasks.size) await Promise.all([...setupTasks]);
    const page = [...sessions.values()].find(session => session.type === 'page' && session.ready);
    if (!page) throw new Error('No debuggable page attached');
    if (options.warmup === 0) {
        phase = 'recording';
        await Promise.all([...sessions.values()].filter(s => s.ready).map(start));
    }
    navigationStartedAt = Date.now();
    await send('Page.navigate', { url: options.url }, page.id);
    page.url = options.url;
    if (options.warmup > 0) {
        await delay(options.warmup * 1000, null, { signal: cancelled.signal });
        phase = 'recording';
        await Promise.all([...sessions.values()].filter(s => s.ready && !s.detached).map(start));
    }
    console.log(`${options.noProfile ? 'Capturing without CPU sampling' : 'Profiling page and workers'} for ${options.seconds}s${options.tests || stopPattern ? ', or until completion' : ''}`);
    try { if (options.tests || stopPattern) {
        const controller = new AbortController();
        await Promise.race([completed, delay(options.seconds * 1000, null,
            { signal: AbortSignal.any([controller.signal, cancelled.signal]) })]);
        controller.abort();
    } else await delay(options.seconds * 1000, null, { signal: cancelled.signal });
    } catch (error) { if (error.name !== 'AbortError') throw error; }
    phase = 'stopping';
    while (setupTasks.size) await Promise.all([...setupTasks]);
    await Promise.all([...sessions.values()].filter(s => s.ready && !s.detached).map(stop));
    try {
        const shot = await send('Page.captureScreenshot', { format: 'png' }, page.id);
        await writeFile(join(out, 'screen.png'), Buffer.from(shot.data, 'base64'));
    } catch (error) { events.push({ type: 'screenshot-error', text: error.message }); }
    if (cancelled.signal.aborted) failures.push('Capture interrupted');
    if (options.tests && (!completion || completion.failed)) failures.push(`Test completion: ${JSON.stringify(completion ?? 'timeout')}`);
    if (stopPattern && !completion) failures.push(`Milestone timeout: ${options['stop-on']}`);
    if (!options.noProfile && (!captured.length || captured.every(item => item.samples === 0))) failures.push('No CPU samples captured');
    const build = options.manifest ? JSON.parse(await readFile(options.manifest, 'utf8')) : null;
    const profilerSha256 = createHash('sha256').update(await readFile(new URL(import.meta.url))).digest('hex');
    await writeFile(join(out, 'capture.json'), JSON.stringify({ options, version, captured, build, profilerSha256,
        navigationStartedAt, completion, failures,
        scope: options.noProfile ? 'Unprofiled browser capture; milestone semantics supplied by caller' : 'CPU sampling, not gameplay performance acceptance' }, null, 2));
    console.log(JSON.stringify({ out, captured, completion, failures }, null, 2));
    if (failures.length) process.exitCode = 1;
} catch (error) {
    failures.push(error.message);
    await writeFile(join(out, 'failure.json'), JSON.stringify({ failures, options }, null, 2));
    console.error(error);
    process.exitCode = 1;
} finally {
    phase = 'closed';
    await writeFile(join(out, 'console.json'), JSON.stringify(events, null, 2));
    await writeFile(join(out, 'chrome.log'), chromeLog.join(''));
    if (socket?.readyState === WebSocket.OPEN) await send('Browser.close').catch(() => {});
    socket?.close();
    for (const item of pending.values()) clearTimeout(item.timer);
    if (chrome.exitCode === null) {
        chrome.kill('SIGTERM');
        await Promise.race([new Promise(resolvePromise => chrome.once('exit', resolvePromise)), delay(3000)]);
    }
    if (chrome.exitCode !== null) await rm(profileDir, { recursive: true, force: true });
}
