/* Windows x86 timing port for the unmodified EEMBC CoreMark algorithms. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include "coremark.h"
static LARGE_INTEGER begin, end, frequency;
ee_u32 default_num_contexts = 1;
void start_time(void) {
    puts("[COREMARK] timing begin"); fflush(stdout);
    QueryPerformanceCounter(&begin);
}
void stop_time(void) {
    QueryPerformanceCounter(&end);
    puts("[COREMARK] timing end"); fflush(stdout);
}
CORE_TICKS get_time(void) {
    return (CORE_TICKS)(((end.QuadPart - begin.QuadPart) * 1000) / frequency.QuadPart);
}
secs_ret time_in_secs(CORE_TICKS ticks) { return (secs_ret)ticks / 1000.0; }
void portable_init(core_portable *p, int *argc, char *argv[]) {
    if (sizeof(ee_ptr_int) != sizeof(void *) || sizeof(ee_u32) != 4 ||
        !QueryPerformanceFrequency(&frequency) || frequency.QuadPart <= 0) {
        puts("ERROR! CoreMark port setup failed"); exit(1);
    }
    p->portable_id = 1;
}
void portable_fini(core_portable *p) { p->portable_id = 0; fflush(stdout); }
