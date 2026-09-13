/*
 * Copyright (C) 2026 The BoxedWine Team
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "boxedwine.h"

#if defined(__TEST) && !defined(BOXEDWINE_MULTI_THREADED)
#include "kscheduler.h"
#include "../cpu/testCPU.h"

extern KList<KThread*> scheduledThreads;

void testSchedulerWakeupProgress() {
    TestContext& context = testContext();
    // Preserve any runner-owned queue entries without running their guest code.
    KList<KThread*> saved;
    while (!scheduledThreads.isEmpty()) {
        auto* node = scheduledThreads.front();
        node->remove();
        saved.addToBack(node);
    }
    KThread* input = context.process->createThread();
    KThread* client = context.process->createThread();
    KThread* server = context.process->createThread();
    scheduleThread(input);
    scheduleThread(client);

    U32 inputTurns = 0;
    // Model a client and server waking each other, then blocking for a reply.
    // A third, continuously runnable input worker must still make progress.
    for (U32 turn = 0; turn < 32; ++turn) {
        KThread* current = scheduledThreads.front()->data;
        unscheduleThread(current);
        if (current == input) {
            ++inputTurns;
            scheduleThread(input);
        } else {
            scheduleThread(current == client ? server : client);
        }
    }
    unscheduleThread(input);
    unscheduleThread(client);
    unscheduleThread(server);
    context.process->deleteThread(input);
    context.process->deleteThread(client);
    context.process->deleteThread(server);
    while (!saved.isEmpty()) {
        auto* node = saved.front();
        node->remove();
        scheduledThreads.addToBack(node);
    }
    if (inputTurns < 8) {
        testFail("IPC wakeups starved runnable input worker: %u turns out of 32", inputTurns);
    }
}
#endif
