// Self time only. Sampling estimates, not inclusive/additive engine timings.
import { readFile } from 'node:fs/promises';
const files = process.argv.slice(2);
if (!files.length) throw new Error('Usage: node summarize-profile.mjs capture/*.cpuprofile');
for (const file of files) {
    const profile = JSON.parse(await readFile(file, 'utf8'));
    const nodes = new Map(profile.nodes.map(node => [node.id, node]));
    const times = new Map();
    let total = 0;
    for (let i = 0; i < (profile.samples?.length ?? 0); i++) {
        const frame = nodes.get(profile.samples[i])?.callFrame;
        if (!frame) throw new Error('Sample references an unknown profile node');
        const us = profile.timeDeltas?.[i] ?? 1000;
        const key = `${frame.functionName || '(anonymous)'} @ ${frame.url}:${frame.lineNumber + 1}`;
        times.set(key, (times.get(key) || 0) + us);
        total += us;
    }
    console.log(JSON.stringify({ file, sampledMs: total / 1000,
        top: [...times].sort((a, b) => b[1] - a[1]).slice(0, 25).map(([name, us]) =>
            ({ name, selfMs: us / 1000, percent: total ? us * 100 / total : 0 })) }, null, 2));
}
