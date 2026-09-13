/* GPL-2.0-or-later. Resolve private pthread command values at build time.
 * Older SDKs use strings; recent SDKs define numeric CMD_* constants.
 * This is a JS library (preprocessed by Emscripten), not a --pre-js file. */
addToLibrary({
    $bwWasmPthreadCommands: {
        run: {{{ typeof CMD_RUN !== 'undefined' ? CMD_RUN : "'run'" }}},
        callHandler: {{{ typeof CMD_CALL_HANDLER !== 'undefined' ? CMD_CALL_HANDLER : "'callHandler'" }}}
    },
    $bwWasmPthreadCommands__postset:
        'globalThis.bwWasmPthreadCommands = bwWasmPthreadCommands;'
});
