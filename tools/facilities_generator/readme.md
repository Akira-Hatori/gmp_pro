运行 facilities_data_generator.py 将创建许多 `.meta` 和 `.metadata` 文件夹。这些文件夹可能让你将 GMP 产品导入到 CCS 中。

所有设置可以在配置文件 `facilities.json` 中找到。

`gmp_fac_install.py` 是设施的安装脚本。

`gmp_fac_clear.bat` 用于重置 `gmp_fac_install.py` 脚本所做的所有操作。

在 CCS 中，你可以在 `Window-Preferences`、`General-Products` 中找到 TI 提供的许多产品。当你需要添加 GMP 时，应该按下"添加"按钮并选择正确的路径。

`gmp_fac_generate_srcs.py` 是一个脚本，用户可以使用它快速创建项目。

用户应该实现一个 `.json` 脚本来指定哪些模块已被调用。

`gmp_fac_config_gui.py` 是一个工具，用于配置源文件。此工具由 AI 工具生成，采用以下提示词。

``` text
请帮我写一个基于python的图形化程序，可以读取类似下面的json文件：
{
    "gmp_source_dic_file": "E:\\lib\\gmp_pro\\tools\\facilities_generator\\gmp_source_dic.json",
    "gmp_core": true,
    "gmp_ctl_core": true,
    "gmp_ctl_motor_control": true,
    "gmp_ctl_digital_power": true,
    "gmp_csp_windows": true,
    "gmp_csp_c28x": true,
    "gmp_csp_stm32": false
}
其中从第二行开始的数据在窗口上都需要创建一个CheckBox用来选择是否启用，每一个CheckBox占用一行，用户可以设置ChcekBox修改对应json文件的设置为true或者false，提示信息用户不可更改，使用Text作为实现容器。提示信息应当在CheckBox的上面。每一行的注释需要显示在页面上，注释信息可以从gmp_source_dic_file变量知识的json文件中的description字段读出，如果description字段不存在则不显示说明，只显示选项的名字，这个json文件的格式如下所示：
[
    {
        "name": "gmp_core",
    "tag" : "GMP CORE",
        "source_path" : [
            "core/"
        ],
        "include_path": [
            "."
        ],
        "description":"Say something."
    },
    {
        "name": "gmp_ctl_core",
    "tag" : "GMP CTL",
        "source_path" :[
            "ctl/framework/",
            "ctl/component/intrinsic/"
        ],
        "include_path": [
            "."
        ],
        "description" : "Say another thing."
    }]
这个窗口提供了打开文件、保存文件、退出软件的基本功能。保存文件覆盖打开的文件，根据CheckBox的选择情况修改各个变量为true或者false。在退出软件时需要询问用户是否保存文件。特别地，在显示提示内容时应当允许自动换行以适应比较长的提示内容。在启动时修改窗口的默认宽度为450像素。
如果需要显示的内容过多，窗口应当显示一个滚动条。
所有的CheckBox应当根据tag标志来分组，分组的标题设置为tag的值。
为整个程序设置热键，Ctrl+S为保存。
```

用户可以通过 `gmp_fac_config_gui.py` 打开 `facility_cfg.json`，然后选择需要的源代码部分。

`facility_cfg.json` 由 `gmp_fac_generate_cfg_json.py` 工具生成。

`gmp_fac_generate_srcs.py` 是一个工具，用于用户生成必要的文件。

总结：

gmp_fac_install.bat 脚本安装gmp 在CCS中的product

gmp_fac_clear.bat 删除由于注册product引入的额外文件（卸载）

gmp_fac_generate_cfg_json.bat 利用gmp_source_dic.json生成facility_cfg.json，方便用户在此模板上进行设置。

gmp_fac_config_gui.bat提供了一个图形化的界面用来编辑facility_cfg.json。

gmp_fac_generate_srcs_example.bat文件提供了一个示例，用来利用facility_cfg.json生成需要的头文件目录：include_paths.txt和需要的所有源文件，放在gmp_src文件夹中。

gmp_fac_generate_cmake_example.bat文件提供了一个示例，可以在提供facility_cfg.json的基础上生成camke文件。

gmp_fac_config_gui_example.bat文件提供了一个示例，可以自动打开facility_cfg.json文件。

> 综合以上两条，可以在创建目标工程时将gmp_fac_config_gui_example.bat，gmp_fac_generate_cmake_example.bat，facility_cfg.json三个文件生成工程需要的cmake文件，并且可以用gmp_fac_config_gui_example.bat文件编辑配置文件。

