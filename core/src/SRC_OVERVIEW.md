# SRC 文件夹概览（面向初学者）

本文档基于你当前打开的 `core/src` 下的若干文件生成，面向电机控制与嵌入式开发的初学者，用通俗语言解释重要名词、逐文件说明，以及如何利用该文件夹开展开发与学习路线。

---

## 一、重要名词（通俗解释）
- **任务 / Task (`gmp_task_t`)**：把“要做的事”封成一个小包（函数 + 周期 + 状态），主循环按时间决定什么时候执行它。类似定时烤菜，每到时间就执行。
- **调度器 / Scheduler (`gmp_scheduler_t`)**：负责管理、轮询和执行任务，相当于厨房里的厨师，按先后和时间安排任务。
- **阻塞/挂起任务（blocking task）**：有些任务需要多次轮次才能完成（返回 BUSY），调度器把它标记为“阻塞”，下次继续同一任务，直到返回 DONE。
- **轮询/Dispatch（`gmp_scheduler_dispatch`）**：主循环里被频繁调用的函数，用来决定并运行该运行哪个任务。
- **时间戳/周期（`period`、`last_run`）**：任务的周期与上次运行时间，用来判断是不是到该运行了。
- **Ring Buffer（环形缓冲）**：一个首尾相接的数组，用于串口/网络等数据临时存储，读写像绕圈。适合 ISR（中断）向主循环传数据。
- **半双工/双工通道（half/duplex）**：通信接口类型。半双工一次只能收或发，双工可同时收发。结构体封装缓冲与长度。
- **AT 命令/解析（`at_device`）**：基于文本的设备命令协议（如 "AT+CMD=..."），解析器负责从接收缓冲取行、识别命令、调用对应 handler。
- **ISR（中断服务例程）**：硬件中断触发的函数，用来快速把数据放进 ring buffer，不做复杂处理。
- **内存块分配（Block allocator）**：把一大块内存按“块”管理的分配器，分配/释放时只改变块头和位图，适合嵌入式静态内存场景。
- **assigned_flag 位图**：一串位表示哪些块已被占用，查找连续空闲块时用到，类似停车场每个车位的占位牌。
- **magic number（魔数）**：写在内存区头部的固定值，用来检测内存头是否被破坏或未初始化。
- **弱符号/弱函数（weak）**：库里提供默认空实现，平台或应用可以重写（实现同名函数），相当于“占位钩子”供你插入初始化或主循环代码。
- **`gmp_base_print` / `default_debug_dev`**：抽象的打印接口；库调用打印，但具体如何输出（串口/主机终端）由你实现并通过 `default_debug_dev` 指定。
- **错误/状态码（`ec_gt` / 全局错误变量）**：全局变量记录最近的错误，便于调试和定位问题。

---

## 二、逐文件作用（基于你打开的文件）

- `gmp_process_mgr.c`
  - 实现了一个简单的时间片/周期调度器：初始化、加入任务、调度分发。
  - 用处：将控制逻辑拆成若干 `gmp_task_t`，由调度器统一管理，方便写周期性或异步任务。

- `gmp_mm_block_memory.c`
  - 实现基于“块”的内存分配器（依赖编译宏启用）：初始化内存区域、按块分配/释放、链表和位图管理、错误码与魔数检测。
  - 用处：在无操作系统或要求确定性分配时使用，减少碎片，适合嵌入式静态内存场景。

- `gmp_std_port.c`
  - 平台/系统相关的接口实现或占位：打印包装、抽象 malloc/free、弱函数（init/mainloop/setup_peripheral 等）。
  - 用处：移植到目标板时需实现或替换这些接口（比如把打印定向到串口）。

- `gmp_std_error_code.c`
  - 定义全局错误/返回码变量（`g_gmp_last_ret`、`g_gmp_last_error`、`g_gmp_last_fatal`）并包含错误显示实现。
  - 用处：统一记录与查询错误，便于调试。

- `gmp_ds_list.c`
  - 当前仅包含头文件，未实现具体链表/数据结构。可扩展为通用链表/队列实现。

- 另外，`gmp_dev_util.c`（你也打开过）实现了 ring buffer、通道初始化、CAN/I2C/半双工初始化等，属于设备层，常与 AT 解析器、中断配合使用。

---

## 三、如何利用 `src` 开发（面向初学者的实用步骤）

1. 阅读头文件
   - 打开并阅读 `gmp_core.h`（及 `core/std` 下的头文件），查找 `gmp_task_t`、`gmp_scheduler_t`、分配宏与 AT 相关类型，理解字段（`handler`、`period`、`last_run`、`is_enabled`）。

2. 搭建最小可运行示例
   - 在应用中：
     - 定义并初始化 `gmp_scheduler_t sched; gmp_scheduler_init(&sched);`
     - 写一个简单任务 handler（返回 `GMP_TASK_DONE`）。
     - 创建并注册任务：`gmp_scheduler_add_task(&sched, &mytask);`
     - 在主循环中反复调用：`gmp_scheduler_dispatch(&sched);`
   - 在 PC/仿真环境先跑通，确保 `gmp_base_print` 有输出。

3. 配置打印与内存策略
   - 决定 `SPECIFY_GMP_DEFAULT_ALLOC`：PC 调试用系统 `malloc`，嵌入式用 block allocator 或自定义静态分配。
   - 实现 `GMP_BASE_PRINT_FUNCTION` 或把 `default_debug_dev` 指向你的串口驱动，保证日志可见。

4. 使用 AT 解析器（若需要串口命令）
   - 准备 `at_device_cmd_t cmd_table[]`，实现命令 handler。
   - 在串口 ISR 中把接收数据推入 ring buffer（调用 `at_device_rx_isr`），在主循环调用 `at_device_dispatch` 解析并执行命令。

5. 测试内存分配器（可选）
   - 分配一段静态内存，调用 `gmp_mem_setup(memory_entry, size_bytes, block_size_unit);`
   - 用 `gmp_block_alloc`/`gmp_block_free` 测试分配释放，或通过宏让 `gmp_base_malloc` 转发到 block allocator。

6. 错误与断言
   - 使用库中的错误变量（如 `g_gmp_last_error`）及 `gmp_base_print` 打印调试信息。
   - 实现或覆盖弱函数（`init`、`mainloop`、`setup_peripheral`）以放入硬件初始化逻辑。

7. 逐步集成与验证
   - 每一步改动后在仿真或目标板上逐步验证：先确认打印，再确认调度与任务执行，最后添加外设中断与 AT 命令处理。

---

## 四、示例代码（最小任务示例，伪代码）
```
// handler 示例
gmp_task_status_t my_task_handler(gmp_task_t* t) {
    gmp_base_print("task run\r\n");
    return GMP_TASK_DONE;
}

// 初始化并注册
void app_init(void) {
    static gmp_task_t mytask;
    mytask.handler = my_task_handler;
    mytask.period = 100; // 单位由 platform 决定（ms / tick）
    mytask.is_enabled = 1;
    mytask.last_run = gmp_base_get_system_tick(); // 如果有此函数
    gmp_scheduler_init(&sched);
    gmp_scheduler_add_task(&sched, &mytask);
}

// 主循环
void app_mainloop(void) {
    for (;;) {
        gmp_scheduler_dispatch(&sched);
    }
}
```

注意：具体类型名、tick 单位与宏请参照头文件定义。

---

## 五、面向你的学习建议（初学路线）
- 学习嵌入式 C：指针、结构体、回调、内存管理。
- 理解实时与调度基础：轮询 vs 中断 vs 任务调度。
- 实践优先：在 PC 上先跑最小示例，熟悉 `gmp_base_print`、任务与 ring buffer。
- 实现一个简单 AT 命令（如 `AT+LED=1`），从串口接收到命令解析并执行，完整串通 ISR → ring buffer → dispatch → handler。
- 阅读 `gmp_core.h` 与 `core/std` 下头文件，找到移植点并实现对应 weak 函数和打印/内存接口。

---

## 六、下一步建议
如果你愿意，我可以为你进一步做下列任意一项：
1) 写一个完整的最小 demo（包含 `main.c`、任务、仿真打印）并给出在主机上运行的步骤；
2) 帮你把 `gmp_base_print` 定向到串口（或主机控制台）并测试 `gmp_scheduler_dispatch`；
3) 指导你实现并测试一个简单的 AT 命令（串口接收到执行）。

请选择你想先做的项或告诉我你想要的其它帮助。
