# CPU Emulation

Boxedwine runs x86 Linux binaries using Tiny Core Linux 15 as the base file system.  The main purpose of Boxedwine is to run the 32-bit version of Wine in order to run 32-bit Windows applications and games.  Wine is not an emulator so it will expect the host to run on an x86 processor in order to run the x86 compiled code of the Windows apps/games.

Boxedwine is an emulator and will emulate x86 instructions.  Because of this it is easy to run Boxedwine on other hardware architectures such as ARM.  The simplest CPU emulation is to decode an x86 instruction then run the code associated with that instruction, for example you can think of a giant switch statement that loops, handling each instruction.  Boxedwine has two main types of CPU emulation, "normal" which is kind of like the giant switch/loop I just mentioned and JIT (Just in Time) which translates x86 instructions to host machine code or WebAssembly at runtime.  The normal CPU emulator is slow but since it doesn't know about the host, it will just work on all architectures.  JIT backends are implemented for x86, x64, ARMv8 (ARM64), and WebAssembly; performance depends on the workload and backend.

The WebAssembly backend contains an x86-to-Wasm JIT in
`source/emulation/cpu/wasm`, available through the
Emscripten `jit`, `multiThreadedJit`, `testJit`, and `testMultiThreadedJit` targets.
It emits Wasm modules at runtime, caches guest registers in Wasm locals, uses
inline software TLB paths, and retains interpreter helpers for unsupported or
exception-sensitive operations. The ordinary `release` target remains an
interpreter build. See [Web CPU development](Web-CPU-Development.md).

All CPU emulation supports x87 (FPU), MMX, SSE and SSE2.

CPU emulation is also well unit tested including comparison to actual hardware results when running with MSVC and 32-bit, see:

https://github.com/danoon2/Boxedwine/tree/master/source/test

## Normal CPU
The normal CPU emulator is the slowest but compatible with all platforms and architectures since it doesn't contain any knowledge of the hosts CPU architecture.  The Emscripten `release` and `test` targets use this interpreter.

The source for the normal CPU emulator can be found here:

https://github.com/danoon2/Boxedwine/tree/master/source/emulation/cpu/normal

The normal CPU emulator will decode a group of x86 instructions where each group is terminated when there is a branching instruction, like jmp, call, ret, etc.  So the groups are usually pretty small, on average about 5 instructions.  After it is decoded, the instructions are copied into "DecodedOp" and stored in KMemoryData.opCache so that can easily re-used.  Of course the code will need to watch the memory for writes in order to invalidate that cache.  The code to handle the cache invalidation is here:

https://github.com/danoon2/Boxedwine/tree/master/source/emulation/softmmu/soft_code_page.cpp

A DecodedOp points to the next DecodedOp, so when a DecodedOp is called it will automatically call the next op in the group.  Because the next op that will be called can be anything (not known at Boxedwine compile time), this will use an indirect call (think virtual call for c++/java).  These are slower than normal direct calls because the host CPU cannot predict where the code will jump to.

The normal CPU can run in single or multi-threaded mode.  For single-threaded mode, there is a scheduler that tries to give each thread some time, but its honestly not that great and can result in stuttering

https://github.com/danoon2/Boxedwine/tree/master/source/kernel/kscheduler.cpp#L168

Multithreading can improve throughput, but the gain depends on the workload and runtime. Correct handling of the lock instruction prefix and x86 memory ordering is essential.  Here is the code that handles that.

https://github.com/danoon2/Boxedwine/tree/master/source/emulation/cpu/common/common_lock.cpp


## JIT
This is the same as the normal CPU emulator but for groups of DecodedOp's that are run more frequently it will recompile that group to host code or WebAssembly.  DecodedOp will contain a pointer to the JIT code for that instruction, so when the main CPU loops calls the next instruction, it will ask the DecodedOp to provide the Normal CPU function or the JIT if it has already been converted.

see: void OPCALL firstDynamicOp(CPU* cpu, DecodedOp* op)
https://github.com/danoon2/Boxedwine/tree/master/source/emulation/cpu/jit/jitCodeGen.cpp#L718

The JIT contains lots of code to properly handle memory and CPU flags for all of the x86 instructions
https://github.com/danoon2/Boxedwine/tree/master/source/emulation/cpu/jit

Each host/platform architecture will need some specific code for the JIT to work, the backends include

- x86/x64: https://github.com/danoon2/Boxedwine/tree/master/source/emulation/cpu/x32
- armv8: https://github.com/danoon2/Boxedwine/tree/master/source/emulation/cpu/armv8
- WebAssembly: https://github.com/danoon2/Boxedwine/tree/master/source/emulation/cpu/wasm
