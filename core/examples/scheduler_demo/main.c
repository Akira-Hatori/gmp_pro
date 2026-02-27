/*
 * Minimal GMP-style scheduler demo (Hello World)
 * - Self-contained example to illustrate how a lightweight scheduler works
 * - Two periodic tasks: one 500ms, one 1000ms
 * - Runs for ~5 seconds then exits
 */

#include <stdio.h>
#include <stdint.h>
#include <time.h>
#include <stdlib.h>
#if defined(_WIN32)
#include <windows.h>
#endif

typedef uint32_t time_gt;

static time_gt gmp_base_get_system_tick_ms(void) {
    /* portable-ish: clock() gives CPU-time, but for a simple demo it's acceptable */
    return (time_gt)((clock() * 1000) / CLOCKS_PER_SEC);
}

typedef enum { GMP_TASK_DONE = 0, GMP_TASK_BUSY = 1 } gmp_task_status_t;

typedef struct gmp_task_s {
    gmp_task_status_t (*handler)(struct gmp_task_s* t);
    time_gt period_ms;
    time_gt last_run_ms;
    int is_enabled;
    /* user data */
    void* user_data;
} gmp_task_t;

#define MAX_TASKS 8

typedef struct {
    gmp_task_t* tasks[MAX_TASKS];
    int task_count;
} gmp_scheduler_t;

void gmp_scheduler_init(gmp_scheduler_t* s) {
    s->task_count = 0;
}

int gmp_scheduler_add_task(gmp_scheduler_t* s, gmp_task_t* t) {
    if (s->task_count >= MAX_TASKS) return -1;
    s->tasks[s->task_count++] = t;
    return 0;
}

/* dispatch: call eligible tasks (cooperative scheduling) */
void gmp_scheduler_dispatch(gmp_scheduler_t* s) {
    time_gt now = gmp_base_get_system_tick_ms();
    for (int i = 0; i < s->task_count; ++i) {
        gmp_task_t* t = s->tasks[i];
        if (!t->is_enabled) continue;
        time_gt elapsed = now - t->last_run_ms;
        if (elapsed >= t->period_ms) {
            gmp_task_status_t st = t->handler(t);
            if (st == GMP_TASK_DONE) {
                t->last_run_ms = now;
            } else {
                /* BUSY: keep last_run unchanged so task can be retried soon */
            }
        }
    }
}

/* Example tasks */
gmp_task_status_t task_a(gmp_task_t* t) {
    int* counter = (int*)t->user_data;
    (*counter)++;
    printf("[Task A] tick %d\n", *counter);
    return GMP_TASK_DONE;
}

/* Task B demonstrates BUSY -> DONE multi-step work */
gmp_task_status_t task_b(gmp_task_t* t) {
    int* state = (int*)t->user_data;
    if (*state < 2) {
        printf("[Task B] working step %d (BUSY)\n", *state + 1);
        (*state)++;
        return GMP_TASK_BUSY;
    }
    printf("[Task B] finished step, returning DONE\n");
    *state = 0;
    return GMP_TASK_DONE;
}

int main(void) {
    gmp_scheduler_t sched;
    gmp_scheduler_init(&sched);

    static gmp_task_t ta;
    static gmp_task_t tb;
    static int a_counter = 0;
    static int b_state = 0;

    ta.handler = task_a;
    ta.period_ms = 500; /* 500 ms */
    ta.last_run_ms = gmp_base_get_system_tick_ms();
    ta.is_enabled = 1;
    ta.user_data = &a_counter;

    tb.handler = task_b;
    tb.period_ms = 1000; /* 1 s */
    tb.last_run_ms = gmp_base_get_system_tick_ms();
    tb.is_enabled = 1;
    tb.user_data = &b_state;

    gmp_scheduler_add_task(&sched, &ta);
    gmp_scheduler_add_task(&sched, &tb);

    printf("GMP-style scheduler demo start\n");
    time_gt start = gmp_base_get_system_tick_ms();
    while (1) {
        gmp_scheduler_dispatch(&sched);
        /* sleep a little to avoid busy loop; in embedded this would be idle */
#if defined(_WIN32)
        Sleep(10);
#else
        struct timespec ts = {0, 10 * 1000 * 1000}; /* 10ms */
        nanosleep(&ts, NULL);
#endif
        if (gmp_base_get_system_tick_ms() - start > 5000) break; /* run ~5s */
    }
    printf("Demo end\n");
    return 0;
}
