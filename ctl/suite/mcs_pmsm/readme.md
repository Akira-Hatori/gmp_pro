# GMP CTL PMSM Motor Control Suite

PMSM id = 0 控制器。

## 摘要

BOOSTXL-3PHGANINV (48-V Three-Phase Inverter With Shunt-Based In-Line Motor Phase Current Sensing Evaluation Module) 用于实现电机驱动。相关说明见：https://www.ti.com/tool/BOOSTXL-3PHGANINV

### 电流与电压测量

1. 电流测量

电流测量使用 $0.005 \,\Omega$ 分流电阻，和 INA240A1 提供 20 倍增益。

2. 电压测量

电压测量增益为
$$
A_v = \frac{4.22 \,k\Omega}{100 \,k\Omega + 4.22 \,k\Omega} = 0.04049127
$$

同时，电压滤波器截止频率为
$$
f_{vc} = \frac{1}{2\pi RC}=\frac{1}{2\pi \times 4.22 \,k\Omega \times 0.033 \,\mu F}= 1.1434\,kHz
$$

3. 电机参数

目标电机为 PMSM，参数存于 `ctl/component/motor_control/preset_motor_param/GBM2804H_100T.h`



## 编码器硬件

系统使用 [AS5048A](https://docs.rs-online.com/0657/A700000006921305.pdf) 作为绝对位置编码器。这是一款带 SPI 接口的 14 位旋转位置传感器。



## 软件结构

GMP CTL motor_control 套件基于 CTL nano 框架，包含带绝对位置编码器的 PMSM 控制器。主要部分定义于 `pmsm_servo.h`，部分初始化代码定义于 `src/pmsm_servo.c` 。

一组调用示例定义在 `implement` 文件夹。`impelement/user_common` 包含 `pmsm_servo` 的基本用法，这些代码与 MCU 无关。与运行平台相关的代码定义在各自文件夹中。

| 文件夹        | 平台                                                     |
| ------------- | -------------------------------------------------------- |
| user_f28x     | [Launch Pad F280039](https://www.ti.com/tool/LAUNCHXL-F280039C) |
| user_simulink | GMP SIL                                                  |
| user_stm32    | [NUCLEO-G474RE](https://www.st.com/en/evaluation-tools/nucleo-g474re.html) |

可在 `impelement/<platform>/ctrl_settings.h` 中更改电机配置。

| 宏                       | 说明                                                      |
| ------------------------ | -------------------------------------------------------- |
| BUILD_LEVEL              | 选择构建级别。开环、电流环、速度环。                       |
| CONTROLLER_FREQUENCY     | 选择控制器频率。                                           |
| CONTROLLER_PWM_CMP_MAX   | 比较器最大值                                               |
| MTR_ENCODER_LINES        | 编码器线数                                                 |
| MTR_ENCODER_OFFSET       | 编码器偏置                                                 |
| MTR_CTRL_CURRENT_LOOP_BW | 控制器电流带宽                                             |
| MTR_CTRL_SPEED_LOOP_BW   | 控制器速度带宽                                             |

控制器参数还通过电机预设和控制器预设读入。

``` C
// 引入电机参数
#include <ctl/component/motor_control/motor_preset/GBM2804H_100T.h>

// 引入电机控制器参数
#include <ctl/component/motor_control/controller_preset/TI_3PH_GAN_INV.h>
```
下一步计划：增加弱磁控制的代码




## GMP SIL 仿真环境

GMP SIL 项目：`gmp_pro\ctl\suite\motor_control\pmsm\projects\motor_control_simulink`

可使用 Visual Studio 2022 打开 `motor_control_simulink.sln`，并使用 MATLAB Simulink 2024 或更高版本打开 `gmp_pmsm_sil_mdl.slx`。

> 注意：
>
>  如果尚未安装 GMP CTL Simulink 库，应先运行 `gmp_pro\slib\install_gmp_simulink_lib.m` 进行安装

应先运行 Visual Studio 解决方案，然后运行仿真模型。

可在 `implement\user_simulink\ctl_interface.h` 中更改 `ctl_fmif_output_stage_routine` 监视例程以监控关键变量。



## C28x 电机控制环境

项目位置：`gmp_pro\ctl\suite\motor_control\pmsm\projects\motor_control_c28x_example`

可使用 CCS12 导入该项目。

如果某些产品不存在，应运行 `gmp_pro\tools\facilities_generator\gmp_fac_install.bat` 来安装这些 TI CCS 产品。

设备外设配置

编码器 SPI 端口、模式

| 信号          | 外设     | GPIO 索引 |
| --------------- | -------- | ---------- |
| SPI CS          | GPIO     | GPIO48     |
| SPI SIMO (PICO) | SPIA     | GPIO8      |
| SPI SOMI (POCI) | SPIA     | GPIO17     |
| SPI CLK         | SPIA     | GPIO9      |

串口打印，波特率 115200 bps

| 信号  | 外设 | GPIO Index |
| ------- | ---------- | ---------- |
| SCIA RX | SCIA       | GPIO28     |
| SCIA TX | SCIA       | GPIO29     |

EPWM 通道，10 kHz PWM

| 信号  | 外设   | GPIO index |
| ------- | ------ | ---------- |
| PWM U H | ePWM1  | GPIO0      |
| PWM U L | ePWM1  | GPIO1      |
| PWM V H | ePWM2  | GPIO2      |
| PWM V L | ePWM2  | GPIO3      |
| PWM W H | ePWM6  | GPIO10     |
| PWM W L | ePWM6  | GPIO11     |

计算时间基周期
$$
Period = \frac{120 \,MHz}{10\,kHz\times 2}=6000
$$

ADC 通道，ADCA 用于 U 相，ADCB 用于 V 相，ADCC 用于 W 相，均为高优先级。

| 信号 | 外设 | ADC 通道 |
| ------ | ---------- | ----------- |
| VDC    | ADC A      | ADC A6      |
| VA     | ADC A      | ADC A2      |
| VB     | ADC B      | ADC B9      |
| VC     | ADC C      | ADC C4      |
| IA     | ADC A      | ADC A11     |
| IB     | ADC B      | ADC B12     |
| IC     | ADC C      | ADC C3      |



## STM32G474 电机控制环境

项目位置：`gmp_pro\ctl\suite\motor_control\pmsm\projects\motor_control_stm32g474_hrtim`

可使用 STM32 CubeMX 编辑本项目，并使用 Keil 打开。每次编译时 Keil 会生成 GMP 文件。

编码器 SPI 接口

| 信号   | 外设 | GPIO     |
| -------- | ---------- | -------- |
| SPI CS   | SPI2       | GPIO B10 |
| SPI SIMO | SPI2       | GPIO B15 |
| SPI SOMI | SPI2       | GPIO B14 |
| SPI CLK  | SPI2       | GPIO B13 |

串口（USART）接口，通过调试器连接。

| 信号    | 外设  | GPIO |
| --------- | ---------- | ---- |
| USART1 TX | USART1     | PA2  |
| USART1 RX | USART1     | PA3  |

HRTIM PWM 通道

| 信号       | 外设         | 应用         | GPIO |
| ------------ | -------------- | ------------ | ---- |
| PWM Phase UH | HRTIM Timer E1 | PWM Phase UH | PC8  |
| PWM Phase UL | HRTIM Timer E2 | PWM Phase UL | PC9  |
| PWM Phase VH | HRTIM Timer A1 | PWM Phase VH | PA8  |
| PWM Phase VL | HRTIM Timer A2 | PWM Phase VL | PA9  |
| PWM Phase WH | HRTIM Timer B1 | PWM Phase WH | PA10 |
| PWM Phase WL | HRTIM Timer B2 | PWM Phase WL | PA11 |

ADC 资源

| 信号 | 外设             | GPIO |
| ------ | --------------- | ---- |
| IA     | ADC1 Channel 1  | PA0  |
| VA     | ADC1 Channel 2  | PA1  |
| IB     | ADC2 Channel 3  | PA6  |
| VB     | ADC2 Channel 3  | PA7  |
| VDC    | ADC2 Channel 12 | PB2  |
| IC     | ADC3 Channel 12 | PB0  |
| VC     | ADC3 Channel 1  | PB1  |

用户界面

| 信号      | 用途        | GPIO |
| ----------- | ----------- | ---- |
| User Button | GPIO 输入   | PC13 |
| User LED    | GPIO 输出   | PA5  |



## STM32G431 电机控制环境



项目路径：`gmp_pro\ctl\suite\motor_control\pmsm\projects\motor_control_stm32g431_tim`

编码器 SPI 接口

| 信号   | 外设 | GPIO |
| -------- | ---------- | ---- |
| SPI CS   | SPI2       | PB1  |
| SPI MOSI | SPI2       | PB15 |
| SPI MISO | SPI2       | PB14 |
| SPI CLK  | SPI2       | PB13 |


串口（USART）接口，通过调试器连接。

| 信号    | 外设  | GPIO |
| --------- | ---------- | ---- |
| USART2 TX | USART2     | PA2  |
| USART2 RX | USART2     | PA3  |

TIM PWM 通道

| 信号       | 外设    | 应用         | GPIO |
| ------------ | ------- | ------------ | ---- |
| PWM Phase UH | TIM1 CH1 | PWM Phase UH | PA8  |
| PWM Phase UL | TIM1 CH1 | PWM Phase UL | PA11 |
| PWM Phase VH | TIM1 CH2 | PWM Phase VH | PC1  |
| PWM Phase VL | TIM1 CH2 | PWM Phase VL | PB0  |
| PWM Phase WH | TIM1 CH3 | PWM Phase WH | PC2  |
| PWM Phase WL | TIM1 CH3 | PWM Phase WL | PB9  |

ADC 资源 ???

| 信号 | 外设      | GPIO |
| ------ | ---------- | ---- |
| IB     | ADC1 IN1   | PA0  |
| UC     | ADC1 IN2   | PA1  |
| UB     | ADC1 IN9   | PC3  |
| IA     | ADC2 IN3   | PA6  |
| IC     | ADC2 IN4   | PA7  |
| UA     | ADC2 IN5   | PC4  |
| VDC    | ADC2 IN6   | PC0  |

用户界面

| 信号      | 用途        | GPIO |
| ----------- | ----------- | ---- |
| User Button | GPIO 输入   | PC13 |
| User LED    | GPIO 输出   | PA5  |
