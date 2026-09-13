/* SPDX-License-Identifier: GPL-2.0-or-later
 * Run from the game's install directory inside the guest Wine prefix.
 * Replaces regs.cmd's six reg.exe processes with the same registry writes.
 * No game code, timing settings, or assets are changed.
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>

static LONG set_string(HKEY key, const char *name, const char *value) {
    return RegSetValueExA(key, name, 0, REG_SZ, (const BYTE *)value,
                          (DWORD)strlen(value) + 1);
}

int main(int argc, char **argv) {
    char directory[MAX_PATH], executable[MAX_PATH], command[MAX_PATH + 2];
    const char *game = argc == 2 ? argv[1] : "popTB.exe";
    DWORD length = GetCurrentDirectoryA(sizeof(directory), directory);
    if (argc > 2 || (strcmp(game, "popTB.exe") && strcmp(game, "D3DPopTB.exe")) ||
        length < 3 || length >= sizeof(directory) || directory[1] != ':' ||
        directory[2] != '\\') {
        fprintf(stderr, "Run populous-start.exe [popTB.exe|D3DPopTB.exe] from the game directory.\n");
        return 2;
    }
    if (directory[length - 1] == '\\' && length > 3) directory[--length] = 0;
    if (length + strlen(game) + 2 > sizeof(executable)) return 2;
    memcpy(executable, directory, length);
    executable[length] = '\\';
    strcpy(executable + length + 1, game); // Length checked above.
    if (GetFileAttributesA(executable) == INVALID_FILE_ATTRIBUTES) {
        fprintf(stderr, "Game executable missing: %s\n", executable);
        return 2;
    }
    HKEY key;
    LONG error = RegCreateKeyExA(HKEY_LOCAL_MACHINE,
        "SOFTWARE\\Bullfrog Productions Ltd\\Populous: The Beginning", 0,
        NULL, 0, KEY_SET_VALUE | KEY_WOW64_32KEY, NULL, &key, NULL);
    if (error == ERROR_SUCCESS) {
        DWORD language = 9, build = 1;
        char drive[3] = { directory[0], ':', 0 };
        error = RegSetValueExA(key, "Language", 0, REG_DWORD, (BYTE *)&language, sizeof(language));
        if (!error) error = RegSetValueExA(key, "BuildTypeCode", 0, REG_DWORD, (BYTE *)&build, sizeof(build));
        if (!error) error = set_string(key, "Version", "1.01");
        if (!error) error = set_string(key, "InstallDrive", drive);
        if (!error) error = set_string(key, "InstallPath", directory);
        if (!error) error = set_string(key, "InstallDirectory", directory + 2);
        RegCloseKey(key);
    }
    if (error) {
        fprintf(stderr, "Populous registry setup failed: %ld\n", error);
        return 1;
    }
    puts("BOXEDWINE_POPULOUS_REGISTRY_READY");
    fflush(stdout);
    STARTUPINFOA startup = {0};
    PROCESS_INFORMATION process = {0};
    startup.cb = sizeof(startup);
    snprintf(command, sizeof(command), "\"%s\"", executable);
    if (!CreateProcessA(executable, command, NULL, NULL, FALSE, 0, NULL,
                       directory, &startup, &process)) {
        fprintf(stderr, "Populous launch failed: %lu\n", GetLastError());
        return 1;
    }
    CloseHandle(process.hThread);
    DWORD exit_code = 1;
    if (WaitForSingleObject(process.hProcess, INFINITE) == WAIT_OBJECT_0)
        GetExitCodeProcess(process.hProcess, &exit_code);
    CloseHandle(process.hProcess);
    return (int)exit_code;
}
