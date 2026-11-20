#!/usr/bin/env python3
"""在 Phase32 独立结果目录复跑 Phase31 Wallet 状态反馈回归。"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PHASE31_DRIVER = ROOT / "func/测试过程/SCFuzzBench公开项目接入/Phase31状态反馈序列扩展.py"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Phase32 下的独立输出目录")
    parser.add_argument("--tag", default="wallet-regression")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("phase31_wallet_driver", PHASE31_DRIVER)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法导入 Phase31 Wallet 回归驱动")
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    # Phase31 driver reads the frozen Phase30B candidate, but all result roots are
    # redirected before main() so its historical Phase31 directory stays read-only.
    driver.RESULT = output
    driver.WALLET_RESULT = output
    driver.RUN_ROOT = output
    driver.EXPANSION_ROOT = output
    sys.argv = [str(PHASE31_DRIVER), "--phase", "wallet-extension",
                "--mode", "state_feedback", "--run-tag", args.tag]
    driver.main()
    print("wallet_regression_status=completed")


if __name__ == "__main__":
    main()
