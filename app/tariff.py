"""已归档炉次冻结曲线的电费试算（纯计算，不读不写任何状态）。

规则：
- 每档 5 分钟，档内功率恒定；kWh = 功率(kW) × 5/60。
- 电价按 24 小时给出且每天重复；档位跨小时（含跨午夜）时，按落入各
  小时的分钟数分摊电费。
- 逐档费用各自四舍五入到两位小数；总费用先汇总**未舍入**的逐档费用，
  再四舍五入到两位（逐档金额之和可能与总费用相差 1 分）。
- 全程使用 Decimal 计算，避免二进制浮点导致的五入误差。
"""

from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

STEP_MINUTES = 5
PRICE_COUNT = 24
MINUTES_PER_DAY = 1440

_CENT = Decimal("0.01")
_SIXTY = Decimal("60")


def _money(value: Decimal) -> float:
    """四舍五入（ROUND_HALF_UP）到两位小数后以数值返回。"""
    return float(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def _nonneg_number(value: Any, label: str) -> Decimal:
    """电价 / 功率元素：必须是非负有限数（拒绝布尔、字符串、NaN/Inf）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}必须是非负数值。")
    if not math.isfinite(float(value)) or float(value) < 0:
        raise ValueError(f"{label}必须是非负有限数。")
    # 经 str 转 Decimal：0.1 等十进制数不会带入二进制浮点误差
    return Decimal(str(value))


def validate_trial_inputs(
    start_minute: Any, prices: Any, powers: Any, step_count: int
) -> tuple[int, list[Decimal], list[Decimal]]:
    """试算入站校验；非法时抛 ValueError（中文信息，路由层转 422）。"""
    if isinstance(start_minute, bool) or not isinstance(start_minute, int):
        raise ValueError("开炉分钟必须是 0～1439 的整数。")
    if not (0 <= start_minute <= MINUTES_PER_DAY - 1):
        raise ValueError("开炉分钟必须是 0～1439 的整数。")

    if not isinstance(prices, list):
        raise ValueError("电价必须是以数组形式给出的 24 个数值。")
    if len(prices) != PRICE_COUNT:
        raise ValueError(
            f"电价必须恰好为 {PRICE_COUNT} 个（按 00～23 时排列），"
            f"当前为 {len(prices)} 个。"
        )
    price_values = [
        _nonneg_number(v, f"{hour:02d} 时电价") for hour, v in enumerate(prices)
    ]

    if not isinstance(powers, list):
        raise ValueError("功率必须是以数组形式给出的逐档功率列表。")
    if len(powers) != step_count:
        raise ValueError(
            f"功率档数必须与冻结曲线等长（{step_count} 档），"
            f"当前为 {len(powers)} 档。"
        )
    power_values = [
        _nonneg_number(v, f"第 {i} 档功率") for i, v in enumerate(powers, start=1)
    ]

    return start_minute, price_values, power_values


def simulate(
    temperatures: list[int],
    start_minute: int,
    prices: list[Decimal],
    powers: list[Decimal],
) -> dict:
    """按冻结温度曲线逐档试算；入参由 validate_trial_inputs 保证合法。"""
    steps: list[dict] = []
    total_kwh = Decimal(0)
    total_cost_exact = Decimal(0)

    for index, (temperature, power) in enumerate(
        zip(temperatures, powers), start=1
    ):
        step_start = (start_minute + (index - 1) * STEP_MINUTES) % MINUTES_PER_DAY
        kwh = power * STEP_MINUTES / _SIXTY

        # 5 分钟的档最多跨过一个整点（含午夜 24:00），用通用循环按分钟分摊
        cost = Decimal(0)
        cursor = start_minute + (index - 1) * STEP_MINUTES
        remaining = STEP_MINUTES
        while remaining > 0:
            hour = (cursor // 60) % PRICE_COUNT
            next_hour_start = (cursor // 60 + 1) * 60
            mins = min(remaining, next_hour_start - cursor)
            cost += power * Decimal(mins) / _SIXTY * prices[hour]
            cursor += mins
            remaining -= mins

        total_kwh += kwh
        total_cost_exact += cost
        steps.append(
            {
                "index": index,
                "temperature": temperature,
                "minutes": STEP_MINUTES,
                "startMinute": step_start,
                "kwh": float(kwh),
                "cost": _money(cost),
            }
        )

    return {
        "startMinute": start_minute,
        "stepCount": len(steps),
        "steps": steps,
        # kWh 不做业务舍入；总费用先汇总未舍入值再舍入
        "totalKwh": float(total_kwh),
        "totalCost": _money(total_cost_exact),
    }
