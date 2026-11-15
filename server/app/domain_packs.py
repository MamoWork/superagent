from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ScoreDimension:
    id: str
    name: str
    weight: float
    description: str


@dataclass(frozen=True)
class DomainPack:
    id: str
    name: str
    description: str
    query_hints: tuple[str, ...]
    scorecard: tuple[ScoreDimension, ...]
    output_schema: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["scorecard"] = [asdict(item) for item in self.scorecard]
        data["query_hints"] = list(self.query_hints)
        return data


CROSSBORDER = DomainPack(
    id="crossborder",
    name="跨境电商",
    description="从需求、竞争、利润、供应与合规五个维度判断一个跨境选品机会。",
    query_hints=(
        "amazon reviews complaints",
        "tiktok shop viral",
        "alibaba supplier price",
        "reddit worth it",
    ),
    scorecard=(
        ScoreDimension("demand", "需求", 0.25, "搜索趋势、评论增速、内容热度、社区抱怨频次。"),
        ScoreDimension("competition", "竞争", 0.20, "首页直接竞品数、评论门槛、价格带、广告密度。"),
        ScoreDimension("margin", "利润", 0.25, "采购价、头程、关税、平台费、退货与尾程。"),
        ScoreDimension("sourcing", "供应", 0.15, "工厂/贸易商识别、MOQ、样品周期、认证与审计。"),
        ScoreDimension("compliance", "合规", 0.10, "CE/FCC/FDA、电池/液体、商标与专利风险。"),
        ScoreDimension("confidence", "证据置信度", 0.05, "来源数量、来源多样性、原文可核对程度。"),
    ),
    output_schema="crossborder_opportunity_v1",
)

SAAS = DomainPack(
    id="saas",
    name="软件 / SaaS",
    description="从痛点强度、付费信号、竞争饱和度与交付可行性判断一个软件机会。",
    query_hints=(
        "struggling with",
        "is there a tool",
        "any recommendations",
        "spreadsheet workaround",
    ),
    scorecard=(
        ScoreDimension("pain", "痛点强度", 0.25, "频率、紧急程度、是否影响收入/时间。"),
        ScoreDimension("willingness_to_pay", "付费意愿", 0.25, "是否已在付费、是否有预算角色。"),
        ScoreDimension("competition", "竞争", 0.20, "直接竞品、1-star 评价、替代方案。"),
        ScoreDimension("feasibility", "交付可行性", 0.20, "MVP 周期、技术风险、依赖。"),
        ScoreDimension("confidence", "证据置信度", 0.10, "来源数量、原文引用、行为信号。"),
    ),
    output_schema="saas_opportunity_v1",
)

GENERAL = DomainPack(
    id="general",
    name="通用",
    description="未指定行业时的通用机会研究。",
    query_hints=(),
    scorecard=(
        ScoreDimension("pain", "痛点强度", 0.35, "抱怨频率与紧急程度。"),
        ScoreDimension("payment", "付费信号", 0.35, "是否已在付费或用 workaround。"),
        ScoreDimension("competition", "竞争", 0.30, "替代方案与进入难度。"),
    ),
    output_schema="general_opportunity_v1",
)

DOMAIN_PACKS: dict[str, DomainPack] = {
    pack.id: pack for pack in (CROSSBORDER, SAAS, GENERAL)
}


def list_packs() -> list[DomainPack]:
    return list(DOMAIN_PACKS.values())


def get_pack(pack_id: str) -> DomainPack:
    try:
        return DOMAIN_PACKS[pack_id]
    except KeyError as exc:
        raise KeyError(f"未知领域包：{pack_id}") from exc
