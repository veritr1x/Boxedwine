// Load the production broker against both Emscripten worker inventories.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('boxedwine-wasm-jit-module-broker.js', import.meta.url), 'utf8');
for (const legacy of [false, true]) {
    const messages = [];
    const active = { postMessage(message) { messages.push(message); } };
    const idle = { postMessage(message) { messages.push(message); } };
    const created = { postMessage(message) { messages.push(message); } };
    const PThread = { pthreads: { 123: active, 456: active }, unusedWorkers: [idle, active],
        getNewWorker() { return created; } };
    if (legacy) PThread.runningWorkers = [active];
    const Module = { preRun: [] };
    let receive;
    const replies = [];
    runInNewContext(source, { Module, PThread, ENVIRONMENT_IS_PTHREAD: false,
        console, setTimeout, clearTimeout, WebAssembly, URLSearchParams,
        HEAP32: new Int32Array(new SharedArrayBuffer(16)),
        ...(legacy ? {} : { bwWasmPthreadCommands: { run: 2, callHandler: 9 } }),
        addEventListener(type, callback) { if (type === 'message') receive = callback; },
        postMessage(message) { replies.push(message); } });
    for (const callback of Module.preRun) callback();
    for (const worker of [active, idle, PThread.getNewWorker()]) {
        assert.equal(typeof worker.bwWasmJitBrokerOriginalPostMessage, 'function');
        const wrapped = worker.postMessage;
        for (const callback of Module.preRun) callback();
        assert.equal(worker.postMessage, wrapped, 'Repeated installation must not rewrap workers');
        worker.postMessage({ cmd: 'unrelated', value: 17 });
    }
    assert.equal(messages.length, 3);
    assert.ok(messages.every(message => message.cmd === 'unrelated' && message.value === 17));
    Module.bwWasmJitBrokerSetDropNextRun(1, 0);
    created.postMessage({ cmd: legacy ? 'run' : 2 });
    assert.equal(messages.length, 3, 'The run interceptor must recognize the selected SDK command');
    receive({ data: { bwWasmJitModuleBroker: { type: 'statsRequest', requestId: 12, token: 'test' } } });
    assert.equal(replies[0].cmd, legacy ? 'callHandler' : 9);
    assert.equal(replies[0].handler, 'bwWasmJitBrokerStatsReply');
    assert.equal(replies[0].args[0], 12);
    console.log(`${legacy ? 'legacy runningWorkers' : 'current pthreads'}: worker inventory and command transport passed`);
}
