# GMP-style Scheduler Demo

这是一个最小示例，展示如何用类似 GMP 的轻量调度器风格组织周期性任务（便于理解 `core/pm` 的思路）。

文件列表：
- main.c: 演示代码
- Makefile: 构建目标（在类 Unix 或 MinGW 下可用）

构建与运行（在 Windows 使用 MinGW/msys 或在 Linux/macOS）:

```sh
cd core/examples/scheduler_demo
make
./scheduler_demo
```

在 Windows 原生命令提示符下（使用 MSVC）可直接用 `cl` 编译：

```cmd
cl /O2 main.c
main.exe
```

演示说明：
- 任务 A: 每 500ms 打印一次计数
- 任务 B: 每 1000ms 做两步工作（通过返回 BUSY 模拟分段执行），然后返回 DONE
- 程序运行约 5 秒后退出

这个 demo 是自包含的，不依赖仓库的其它头文件；用它可以快速理解调度器 `dispatch` 的基本行为：
- 周期判断（基于系统 tick）
- 协作式任务（任务短时间完成或返回 BUSY 分多次完成）

下一步建议：
- 我可以把这个 demo改写为直接调用 `core/pm` 中的实际类型和 API（如果你想在真实 GMP core 实现上跑），或者把示例扩展为带 `ringbuf` 的串口模拟。告诉我你想要哪个方向。
