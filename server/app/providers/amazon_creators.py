from __future__ import annotations

import asyncio
from typing import Any

from app.providers.base import ProviderError, SourceProvider
from app.providers.util import make_signal_id
from app.schemas import ProviderHealth, ProviderInfo, SearchQuery, Signal

try:  # python-amazon-paapi exposes the Amazon Creators API client.
    from amazon_creatorsapi import AmazonCreatorsApi, Country
    from amazon_creatorsapi.errors import (
        AccessDeniedError,
        AmazonCreatorsApiError,
        AuthenticationError,
        InvalidArgumentError,
        ItemsNotFoundError,
        RequestError,
        TooManyRequestsError,
    )
    from amazon_creatorsapi.models import SearchItemsResource
except ImportError:  # pragma: no cover - exercised only in minimal installs
    AmazonCreatorsApi = None
    Country = None
    SearchItemsResource = None
    AccessDeniedError = Exception
    AmazonCreatorsApiError = Exception
    AuthenticationError = Exception
    InvalidArgumentError = Exception
    ItemsNotFoundError = Exception
    RequestError = Exception
    TooManyRequestsError = Exception

RESOURCES = (
    "ITEM_INFO_DOT_TITLE",
    "ITEM_INFO_DOT_BY_LINE_INFO",
    "ITEM_INFO_DOT_FEATURES",
    "OFFERS_V2_DOT_LISTINGS_DOT_PRICE",
    "OFFERS_V2_DOT_LISTINGS_DOT_IS_BUY_BOX_WINNER",
    "CUSTOMER_REVIEWS_DOT_COUNT",
    "CUSTOMER_REVIEWS_DOT_STAR_RATING",
    "BROWSE_NODE_INFO_DOT_WEBSITE_SALES_RANK",
)


class AmazonCreatorsProvider(SourceProvider):
    """Amazon product search through the official Creators API.

    Credentials come from environment variables and are never persisted or
    returned by the API. No scraping is attempted when credentials are absent.
    """

    def __init__(
        self,
        credential_id: str | None = None,
        credential_secret: str | None = None,
        tag: str | None = None,
        version: str = "3.1",
        country: str = "US",
        timeout: float = 30.0,
    ) -> None:
        self.credential_id = credential_id or ""
        self.credential_secret = credential_secret or ""
        self.tag = tag or ""
        self.version = version
        self.country = country.strip().upper() or "US"
        self.timeout = timeout
        configured = bool(
            AmazonCreatorsApi
            and self.credential_id
            and self.credential_secret
            and self.tag
        )
        self.info = ProviderInfo(
            id="amazon.creators",
            name="Amazon 商品",
            group="marketplace",
            capabilities=["search"],
            auth="api_key",
            status="ready" if configured else "not_configured",
            cost="byo_key",
            rate_limit={"requests": 1, "window_seconds": 1},
            note=(
                f"Amazon Creators API · {self.country} 站点"
                if configured
                else "需要 OPPORTUNITY_AMAZON_CREDENTIAL_ID / SECRET / TAG"
            ),
        )

    async def health(self) -> ProviderHealth:
        if AmazonCreatorsApi is None:
            return ProviderHealth(
                id=self.info.id,
                status="not_configured",
                detail="未安装 python-amazon-paapi，请执行 pip install -r requirements.txt。",
            )
        missing = [
            name
            for name, value in (
                ("OPPORTUNITY_AMAZON_CREDENTIAL_ID", self.credential_id),
                ("OPPORTUNITY_AMAZON_CREDENTIAL_SECRET", self.credential_secret),
                ("OPPORTUNITY_AMAZON_TAG", self.tag),
            )
            if not value
        ]
        if missing:
            return ProviderHealth(
                id=self.info.id,
                status="not_configured",
                detail="缺少环境变量：" + "、".join(missing),
            )
        return ProviderHealth(
            id=self.info.id,
            status="ready",
            detail=f"亚马逊 {self.country} 站点（仅检查配置，不发起请求）",
        )

    async def search(self, query: SearchQuery) -> list[Signal]:
        if AmazonCreatorsApi is None:
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                "未安装 python-amazon-paapi。",
                "执行 pip install -r requirements.txt。",
            )
        if not (self.credential_id and self.credential_secret and self.tag):
            raise ProviderError(
                "PROVIDER_NEEDS_AUTH",
                "Amazon Creators API 未配置凭据。",
                "设置 OPPORTUNITY_AMAZON_CREDENTIAL_ID、"
                "OPPORTUNITY_AMAZON_CREDENTIAL_SECRET、OPPORTUNITY_AMAZON_TAG。",
            )
        try:
            payload = await asyncio.wait_for(
                asyncio.to_thread(self._sync_search, query),
                timeout=self.timeout + 30,
            )
        except asyncio.TimeoutError as exc:
            raise ProviderError(
                "PROVIDER_TIMEOUT",
                "Amazon Creators API 查询超时。",
                "稍后重试；不要循环重试。",
            ) from exc
        return payload

    def _sync_search(self, query: SearchQuery) -> list[Signal]:
        country = getattr(Country, self.country, None)
        if country is None:
            country = self.country
        api = None
        try:
            api = AmazonCreatorsApi(
                credential_id=self.credential_id,
                credential_secret=self.credential_secret,
                version=self.version,
                tag=self.tag,
                country=country,
                timeout=(10, self.timeout),
                retries=1,
            )
            result = api.search_items(
                keywords=query.text,
                search_index="All",
                item_count=min(query.limit, 10),
                resources=list(RESOURCES),
            )
        except TooManyRequestsError as exc:
            raise ProviderError(
                "PROVIDER_RATE_LIMITED",
                "Amazon Creators API 限流。",
                "稍后重试；不要换账号或密钥反复请求。",
                retry_after_seconds=300,
            ) from exc
        except (AuthenticationError, AccessDeniedError) as exc:
            raise ProviderError(
                "PROVIDER_NEEDS_AUTH",
                f"Amazon Creators API 认证失败：{exc}",
                "核对凭证、版本与国家站点是否匹配。",
            ) from exc
        except InvalidArgumentError as exc:
            raise ProviderError(
                "PROVIDER_BAD_REQUEST",
                f"Amazon Creators API 参数无效：{exc}",
                "尝试更短的商品关键词。",
            ) from exc
        except ItemsNotFoundError:
            return []
        except RequestError as exc:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                f"Amazon Creators API 请求失败：{exc}",
                "稍后重试。",
            ) from exc
        except AmazonCreatorsApiError as exc:
            raise ProviderError(
                "PROVIDER_ERROR",
                f"Amazon Creators API 错误：{exc}",
            ) from exc
        finally:
            if api is not None:
                api.close()

        signals: list[Signal] = []
        for item in result.items or []:
            url = (item.detail_page_url or "").strip()
            title = self._title(item)
            if not url or not title:
                continue
            price, currency = self._price(item)
            rating = getattr(item.customer_reviews, "star_rating", None)
            rating_value = getattr(rating, "value", None)
            reviews = getattr(item.customer_reviews, "count", None)
            rank = getattr(
                getattr(item.browse_node_info, "website_sales_rank", None),
                "sales_rank",
                None,
            )
            quote_parts = []
            if price is not None:
                quote_parts.append(f"价格 {price} {currency}".strip())
            if rating_value is not None:
                quote_parts.append(f"评分 {rating_value}/5")
            if reviews is not None:
                quote_parts.append(f"{int(reviews)} 条评价")
            if rank is not None:
                quote_parts.append(f"类目销量排名 {rank}")
            signals.append(
                Signal(
                    id=make_signal_id(self.info.id, url, title),
                    provider_id=self.info.id,
                    source_type="product",
                    source_url=url,
                    title=title,
                    quote=" · ".join(quote_parts) or "Amazon 商品结果。",
                    metrics={
                        "asin": item.asin,
                        "price": price,
                        "currency": currency,
                        "rating": rating_value,
                        "reviews": reviews,
                        "sales_rank": rank,
                        "country": self.country,
                        "total_results": result.total_result_count,
                    },
                )
            )
        return signals

    @staticmethod
    def _title(item: Any) -> str:
        value = getattr(getattr(item.item_info, "title", None), "display_value", None)
        return str(value or "").strip()[:300]

    @staticmethod
    def _price(item: Any) -> tuple[float | None, str | None]:
        listings = getattr(item.offers_v2, "listings", None)
        if not isinstance(listings, list) or not listings:
            return None, None
        listing = next(
            (row for row in listings if getattr(row, "is_buy_box_winner", False)),
            listings[0],
        )
        money = getattr(getattr(listing, "price", None), "money", None)
        if money is None:
            return None, None
        return (
            getattr(money, "amount", None),
            getattr(money, "currency", None)
            or getattr(money, "display_amount", None),
        )
