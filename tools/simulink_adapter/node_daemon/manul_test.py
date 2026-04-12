# manual_test.py
from matlab_worker import SimulinkWorker
import json

def run_manual_test():
    # 1. 明确你要跑的 Simulink 模型名（不带 .slx 后缀）
    # 注意：模型名需与 .slx 文件名一致（去掉后缀）
    TARGET_MODEL = "MCS_STD_PMSM_MODEL_2022b"
    TARGET_MODEL_PATH = r"D:\WorkDocuments\Github\gmp_pro\ctl\suite\mcs_pmsm_nt\project\simulate\MCS_STD_PMSM_MODEL_2022b.slx"

    # 2. 模拟 Agent 生成的电控参数（确保这些变量名与 Simulink 模型或初始化 .m 脚本中的变量名一致）
    agent_proposed_params = {
        "Target_Speed": 1500.0,
        "Kp_spd": 0.52,
        "Ki_spd": 0.015,
        "Load_Torque": 2.0
    }

    # 3. 初始化 Worker (这会连接到你刚才 ShareEngine 的 MATLAB)
    worker = SimulinkWorker()

    # 4. 发起调用
    print("\n" + "="*50)
    print(" >>> 开始手动测试流程 <<<")
    print("="*50)
    
    final_result = worker.run_simulation(
        model_name=TARGET_MODEL,
        params=agent_proposed_params,
        model_path=TARGET_MODEL_PATH,
        result_vars=["Target_Speed", "Kp_spd", "Ki_spd", "Load_Torque"],
    )

    # 5. 打印结构化回传结果
    print("\n" + "="*50)
    print(" >>> 最终 Agent 将收到的 JSON 数据 <<<")
    print("="*50)
    print(json.dumps(final_result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    run_manual_test()