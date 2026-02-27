# General Motor Platform (GMP) Controller Template Library (CTL) module

欢迎使用 GMP CTL！

## 概述

GMP CTL 提供了一组用于快速创建和访问控制器的工具。由于 GMP 是跨平台库，CTL 模块便于用户为 PC 仿真、Process In Loop (PIL)、Hardware In Loop (HIL)、Real-Time Controller (RTC) 设计创建控制器。

CTL 的基本结构如下。

| Submodule            | Folder Path | 简要说明                                                |
| -------------------- | ----------- | ------------------------------------------------------- |
| CTL component        | `component` | 该文件夹（子模块）提供各种控制器组件。所有组件存放在若干子文件夹中。每个子文件夹包含相同的源文件（用于初始化函数或一些基础支持函数），存放在 `component/src`，并以子模块名称命名。如果用户需要调用某些控制器组件，只需包含这些头文件，然后将相应的源文件添加到项目的编译源列表。 |
| CTL framework        | `framework` | 该文件夹包含预定义的控制器框架。用户可使用这些框架高效且便捷地创建标准实时控制器原型。每个框架提供一组需要由用户按时调用的函数，以及一组需要由用户实现的函数原型。通过这种方式，用户可以将框架插入到自己的项目中。 |
| CTL controller suite | `suite`     | 该文件夹包含一些预定义的控制器套件，以及这些套件的示例。用户可以通过控制器套件快速创建实时控制器应用。 |
| FPGA support         | `fpga`      | 该文件夹提供一些以 HLS 或 Verilog 代码实现的控制器工具。用户可使用这些代码实现 FPGA 实时控制器。 |
| controlled plants    | objects     | 该文件夹包含一系列控制对象。用户可通过此子模块实现仿真。 |


## 控制器类型

在 GMP CTL 子模块中，有两种常用类型：`ctrl_gt`、`parameter_gt`。

`ctrl_gt` 表示控制律计算类型，对于微处理器通常为定点数；对于某些高性能微处理器通常为浮点数；在某些仿真环境下通常为双精度浮点数。与 `ctrl_gt` 相关的类型应提供足够的计算速度和精度。通常对于 DSP 或其他微控制器，建议将 int32_t@Q24 作为 `ctrl_gt` 类型。

若需创建 `ctrl_gt` 类型变量，应使用 `float2ctrl(x)` 宏来初始化，x 应为浮点数。示例如下：

``` C
ctrl_gt a_fixed_point_number = float2ctrl(1.0f);
```

此外，`ctrl_gt` 与其他类型支持加（`+`）和减（`-`）运算，但用户不应直接使用乘（`*`）和除（`/`）。应使用 `gmp_mpy` 和 `gmp_div` 函数代替。相关定义见 `ctl/component/common/gmp_math.h` 文件。

`parameter_gt` 表示参数存储类型。对于微处理器该类型至少为浮点数；对于某些高性能微处理器可能为双精度。此类型用于保存控制器的源参数，控制器初始化函数可使用这些变量来初始化控制器参数。所有 `parameter_gt` 类型的变量应支持浮点数所有的数学运算。


## CTL 函数命名规范

CTL 模块中的所有函数以 `ctl_` 开头，所有组件至少具有三个函数：

| 基本函数                 | 说明                     |
| ------------------------ | ------------------------ |
| `ctl_init_<ModuleName>`  | 初始化并分配内存         |
| `ctl_setup_<ModuleName>` | 配置组件                 |
| `ctl_step_<ModuleName>`  | 执行组件步进             |

一些复杂组件还具有以下函数

| 扩展函数                  | 说明                                                         |
| ------------------------ | ------------------------------------------------------------ |
| `ctl_input_<ModuleName>`   | 输入或单位转换，将输入数据复制到组件。                        |
| `ctl_output_<ModuleName>`  | 获取组件输出。                                               |
| `ctl_prestep_<ModuleName>` | 一些模块具备提前运行的内容，这个函数需要在 step 之前调用     |
| `ctl_bind_<ModuleName>`    | 在初始化时将器件和其他的器件绑定                             |
| `ctl_set_<ModuleName>`     | 设置模块参数                                                 |
| `ctl_get_<ModuleName>`     | 获取模块的参数                                               |

对于控制器框架函数应当用 `ctl_fm_` 作为开头，其中需要用户定义的函数以 `ctl_fmif_` 作为开头，意为框架接口。

CTL 中使用的数学常数以 `CTL_CONST_` 打头，分数的分数线用 `OVER_` 表示，有特殊含义的符号用特殊符号标记。

## 套件

在 CTL 模块中提供了数字电源控制器和电机控制器两个基本控制器的类型，并且支持新能源光伏控制器。

这里的难点，也是下一步需要测试的内容：让 GMP 库能够兼容定点数、浮点数、FPGA-HLS 的特殊类型，并且为将来生成代码做好准备。
