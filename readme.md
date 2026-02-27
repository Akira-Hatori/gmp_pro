# 通用电机平台 (GMP) 库 手册摘要

GMP 是一个轻量易用的库，可帮助你轻松实现控制器。

![GMP 徽标](manual/img/GMP_LOGO.png)

GMP 包含一组工具，可在指定文件夹中找到。

| 文件夹 | 摘要 |
| ------- | :------- |
| core/   | 此文件夹提供整库及用户使用的一组基础组件，例如工作流及其调度、内存管理、IO 设备抽象等。 |
| csp/    | 该文件夹包含所有芯片支持信息。这些预定义有助于你更方便地使用库。 |
| ctl/    | 控制器模板库。该文件夹不仅提供基础组件，还提供大量控制器及其工作流代理。 |
| cctl/ | 基于类的控制器模板库。该文件夹提供一系列 C++ 类控制器和一个模拟器。 |
| vctl/ | 基于 Verilog 的控制器模板库。该文件提供用于控制器设计的示例代码。 |
| ext/    | 库的扩展模块。该文件夹包含许多基于 GMP 内核的设备，这些扩展可帮助你快速、便捷地部署应用。 |

## 安装 GMP 产品

如果需要安装 GMP 产品，请先安装下列软件，以便安装过程顺利进行。

git : https://git-scm.com/downloads

python: https://www.python.org/downloads/

然后运行脚本 `install_gmp.bat`。该脚本将帮助你安装并注册 GMP 产品。

该脚本会创建环境变量 `GMP_PRO_LOCATION`，指向 GMP 库根路径。建议在 CCS 或 Visual Studio 中基于该环境变量添加源文件或包含路径。

## 安装 GMP Simulink SIL 模块

如果你的 MATLAB 版本高于 2022b，可通过运行安装 m 文件来安装 GMP Simulink 模块。

`<GMP ROOT>\slib\install_gmp_simulink_lib.m`

## 开始一个 GMP 项目

+ 作为 GMP 用户，你可以使用完整的跨平台服务。

### 准备必要文件

应将 `<GMP ROOT>\quick_start\gmp_file_generator` 文件夹中的所有文件复制到你自己的项目目录。

运行脚本 `gmp_fac_config_gui.bat` 可配置所需模块。

然后运行脚本 `gmp_fac_generate_src.bat` 可得到所需的所有文件，并生成一个包含应添加到包含路径的路径的 txt 文件。建议将生成代码脚本作为编译准备步骤。

目前，应在 `<GMP ROOT>/quick_start/usr` 中选择一个用户文件模板。若要启动 SIL 项目，可将 `ctl_simulation_mtr_model` 文件夹复制到项目文件夹；若要启动控制器项目，可复制 `ctl_nano_framework_model` 文件夹到项目中。

然后将该用户文件添加到包含路径搜索选项中。

### 让 GMP 代码在你的项目中运行

现在调用 GMP，使 GMP 框架运行。

如果主源文件是 C 源文件，请添加 `core/gmp_core.h`，如下所示。

``` C
#include <core/gmp_core.h>
```

如果主源文件是 C++ 源文件，请添加 `core/gmp_core.hpp`，如下所示。

``` C++
#include <core/gmp_core.hpp>
```

现在，你可以在主函数中调用 `gmp_entry()` 函数，就像下面的代码所示。

现在，你可以在主函数中调用 `gmp_entry()` 函数，就像下面的代码所示。

``` C++
void main (void)
{
	// 执行你的准备代码

	// ...

	// 准备进入 GMP
	gmp_base_entry(); // 调用 GMP 库

	// 其他事项。
	// 但代码永远不会执行到此处。
}
```

> 注意！当 `gmp_entry()` 被调用时，该函数可能不会返回。通常此函数应在所有初始化代码完成后调用， 

### 尽情使用！

现在你可以基于 GMP 框架实现应用。这些代码可添加在 `ctl_main.cpp` 和 `user_main.cpp` 中。

+ 作为 GMP-CTL 用户，你可以禁用所有附加功能，仅使用 xplatform（跨平台）CTL 模块。

我们将在下一个版本中支持该模式。

## GMP 核心模块简介

`gmp_base_` 是 GMP 核心模块的一般前缀。

``` C++
// 获取当前系统时钟
time_gt gmp_base_get_system_tick(void);

// 断言函数
gmp_base_assert();

// 指示该函数尚未实现
gmp_base_not_impl();
```

`gmp_hal_` 是 GMP HAL（硬件抽象层）模块的一般前缀。

`ctl_` 是 GMP CTL 模块的一般前缀。

`ctl_init_` 是 GMP CTL 模块初始化函数的前缀。

`ctl_step_` 是 GMP CTL 模块控制器函数的前缀。该名称表示控制器的离散步进到下一状态。
