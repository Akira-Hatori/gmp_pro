# GMP Motor Control & Power Electronics Suite 开发指南

## 1. 概览

### 1.1 文件夹简介
`ctl/suite` 文件夹是整个 GMP (General Motor Platform) 项目的核心应用示例库。它包含了一系列针对不同电力电子拓扑（如 Buck/Boost 变换器、逆变器）和电机控制（如 PMSM、ACIM）的完整参考设计。

作为一个初学者，你可以把这里看作是一个“实战题库”或“实验室”。每一个子文件夹（如 `mcs_pmsm`）代表一个具体的实验项目，里面包含了从底层驱动配置到上层控制算法的所有代码。

### 1.2 命名规则
文件夹前缀代表了应用领域：
*   **mcs_**: Motor Control Suite（电机控制套件）。例如 `mcs_pmsm` (永磁同步电机)、`mcs_pmsm_smo` (无感滑模观测器)。
*   **dps_**: Digital Power Supply（数字电源）。例如 `dps_buck` (降压变换器)、`dps_boost` (升压变换器)。
*   **pgs_**: Power Grid System（并网/光伏系统）。例如 `pgs_3ph_grid_inverter` (三相并网逆变器)。

---

## 2. 详细内容解析

下面列出各主要文件夹的功能及你的学习重点：

### 2.1 核心学习路径
作为初学者，建议按照以下顺序进行学习和开发：

1.  **入门 (dps_buck / dps_boost)**: 学习最简单的电力电子拓扑。
    *   **目标**: 理解 PWM 生成、ADC 采样、PID 控制闭环。
    *   **文件**: `dps_buck/implement/common/ctl_main.c`
2.  **进阶 (mcs_pmsm)**: 电机控制的“Hello World”。
    *   **目标**: 掌握 FOC (磁场定向控制)、SVPWM、坐标变换 (Park/Clark)。
    *   **文件**: `mcs_pmsm` 下的内容。
3.  **高级**: 无感控制 (`mcs_pmsm_smo` / `hfi`) 或并网逆变 (`pgs_...`)。

### 2.2 文件夹详情

| 文件夹名 | 说明 | 学习价值 |
| :--- | :--- | :--- |
| **mcs_pmsm** | **永磁同步电机基准控制** <br> 包含有感 FOC 控制、速度环/电流环。 | **⭐⭐⭐⭐⭐ (必学)** <br> 所有的电机控制基础都在这里。你将学习如何读取编码器、校准 ADC、配置 FOC 算法。 |
| **mcs_pmsm_smo** | **PMSM 无感滑模控制** <br> 去掉位置传感器，用算法估算角度。 | ⭐⭐⭐⭐ <br> 进阶内容，适合学习观测器设计。 |
| **mcs_pmsm_hfi** | **PMSM 高频注入** <br> 零低速下的无感控制技术。 | ⭐⭐⭐ <br> 难度较大，暂不推荐初学。 |
| **dps_buck** | **Buck 降压变换器** <br> 输出电压低于输入电压的 DC-DC。 | **⭐⭐⭐⭐ (必学)** <br> 结构简单，适合学习 PID 调节电压/电流的基本原理。 |
| **dps_boost** | **Boost 升压变换器** <br> 输出电压高于输入电压的 DC-DC。 | ⭐⭐⭐⭐ <br> 同上。 |
| **pgs_3ph_grid_inverter** | **三相并网逆变器** <br> 将直流电变为交流电并入电网。 | ⭐⭐ <br> 涉及锁相环 (PLL) 和并网标准，初学者可稍后看。 |

---

## 3. 开发架构与文件结构

GMP 采用了一套**平台无关**的开发架构。这意味着核心控制代码（算法）和底层硬件代码（驱动）是分离的。

### 3.1 目录结构详解 (以 `mcs_pmsm` 为例)

一个典型的 Suite 项目包括以下部分：

```text
mcs_pmsm/
├── readme.md               # 项目说明 (硬件连接、参数计算)
├── implement/              # 【源码核心】
│   ├── common/             # [平台无关] 通用控制逻辑
│   │   ├── ctl_main.c      # 控制主程序 (初始化控制器、调度算法)
│   │   ├── user_main.c     # 用户应用层 (LED、按键、通信)
│   │   └── ...
│   ├── stm32g431/          # [平台相关] STM32G4 硬件接口实现
│   │   ├── xplt.peripheral.c # 硬件抽象层实现 (ADC/PWM配置的具体代码)
│   │   └── ...
│   ├── f280049c/           # [平台相关] TI C2000 硬件接口实现
│   └── simulate/           # [仿真] PC端仿真实现
└── project/                # 【工程文件】
    ├── stm32g431/          # STM32 CubeMX / Keil / IAR 工程
    ├── f280049c/           # TI CCS 工程
    └── motor_control_simulink/ # Simulink 仿真模型
```

### 3.2 关键文件说明

1.  **`implement/common/ctl_main.c` (控制核心)**
    *   **作用**: 定义控制器对象，进行算法初始化。
    *   **关键函数**:
        *   `ctl_init()`: 初始化 ADC 校准、编码器、PID 参数、滤波器。
        *   `ctl_dispatch()` (在 .h 中): 在中断中被调用的核心函数，执行一次控制计算。
    *   **示例**:
        ```c
        // 这是一个典型的初始化流程
        void ctl_init() {
            ctl_disable_output(); // 安全第一：先关PWM
            ctl_init_adc_calibrator(...); // 校准零点
            ctl_init_spd_calculator(...); // 初始化速度计算
            // ...
        }
        ```

2.  **`implement/common/user_main.c` (用户逻辑)**
    *   **作用**: 处理慢速任务，如状态机切换、LED 闪烁、串口打印。
    *   **关键函数**: `mainloop()`

3.  **`implement/<platform>/xplt.peripheral.c` (硬件抽象)**
    *   **作用**: 将不同芯片的 API 统一包装。例如，无论是 STM32 还是 DSP，`ctl_set_pwm_duty()` 这个函数的名字是一样的，但在这个文件里的实现不同。

---

## 4. 如何开始开发 (保姆级教程)

假设你手头有一块 **STM32G431** 开发板（常见的电机控制芯片），你想跑通 PMSM 电机控制。

### 第一步：环境准备
1.  安装 **Keil MDK** 或 **STM32CubeIDE**。
2.  安装 **STM32CubeMX** (如果需要修改引脚配置)。
3.  阅读 `mcs_pmsm/readme.md`，了解硬件连接（电流采样电阻接哪、电机线接哪）。

### 第二步：编译与下载
1.  进入 `mcs_pmsm/project/stm32g431/MDK-ARM` 目录。
2.  打开工程文件 (`.uvprojx`)。
3.  点击编译。你会发现工程引用了 `implement/common` 和 `implement/stm32g431` 下的源码。
4.  下载程序到开发板。

### 第三步：调试与运行
GMP通常使用 `BUILD_LEVEL` (构建层级) 的概念来进行分步调试。这通常在 `ctl.config.h` 或类似的配置文件中定义（有时也在 `ctl_main.c` 的宏定义中）。

*   **Level 1: 开环测试**
    *   **目的**: 验证 PWM 输出正常，逆变器正常，电机能转（但不稳）。
    *   **现象**: 给定一个固定频率和电压矢量，电机应该“盲转”。

*   **Level 2: 电流环测试 (FOC核心)**
    *   **目的**: 验证电流采样正确，PID 参数合理。
    *   **操作**: 给定 Iq=0, Id=固定值。锁住转子不动。

*   **Level 3: 速度环测试**
    *   **目的**: 完整的闭环控制。
    *   **操作**: 设定目标速度，电机应能快速跟随。

### 第四步：修改参数
打开 `implement/common/ctl_main.c`，你可以修改：
*   **PID 参数**: `Kp`, `Ki`。
*   **频率限制**: `ctl_init_const_slope_f_controller` 中的斜率。
*   **保护阈值**: 过流、过压保护值。

## 5. 致大学生的建议

1.  **不要被代码量吓到**：只关注 `ctl_main.c` 中的流程。底层的繁琐配置（如寄存器操作）已被封装好，初期只需理解原理。
2.  **理论结合实践**：
    *   书上讲 PWM 调制 -> 去看 `ctl_main.c` 里怎么给 PWM 赋值。
    *   书上讲 PID -> 去看 `ctl_init` 里怎么设 `Kp`, `Ki`。
    *   书上讲 坐标变换 -> 搜索代码里的 `Park`, `Clark` 变换函数。
3.  **善用工具**：学会使用 STM32CubeMonitor 或串口绘图工具观察变量（如 `Id`, `Iq`, `Speed`）的波形，这对调试控制系统至关重要。

祝你在电机控制的世界里探索愉快！
