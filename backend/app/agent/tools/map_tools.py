"""
地图工具集：封装高德地图 / 百度地图开放平台真实 HTTP API。
- 全部使用 httpx.AsyncClient 异步调用，严禁写死假数据。
- 未在 .env 配置 key 时，返回明确中文错误提示，不抛异常中断 Agent。
  【为什么？】工具抛异常会打断 Agent 的思考循环；返回错误描述文本，
  大模型能读懂"调用失败了"，再决定怎么回答用户。
- 所有函数均为 LangChain @tool 工具，description 用中文描述用途与参数。
"""
import hashlib

import httpx
from langchain_core.tools import tool

from app.config import settings
from app.utils.logger import logger


# ---------- 通用超时与客户端工厂 ----------
# 统一超时 10 秒，避免某个地图接口挂死拖垮整个 Agent 调用链
def _make_client() -> httpx.AsyncClient:
    """构造一个带统一超时的异步 HTTP 客户端"""
    return httpx.AsyncClient(timeout=10.0)


# ============================================================
# 高德地图工具
# ============================================================
@tool
async def amap_geocode(address: str, city: str = "") -> str:
    """高德地理编码：把结构化地址（如"南京市玄武区xx路1号"）转换为经纬度及省市区信息。

    参数:
        address: 待解析的结构化地址，必填，例如"北京市朝阳区阜通东大街6号"
        city:    可选，指定城市（提高解析准确度），例如"北京"
    """
    if not settings.amap_key:
        return "高德地图API未配置：请在 .env 中设置 AMAP_KEY。"

    base = "https://restapi.amap.com/v3/geocode/geo"
    params = {"key": settings.amap_key, "address": address}
    if city:
        params["city"] = city

    try:
        # async with：发完请求自动关闭 HTTP 客户端连接，防止连接泄漏
        async with _make_client() as client:
            resp = await client.get(base, params=params)
            resp.raise_for_status()  # HTTP 状态码非 2xx 时直接抛异常
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.exception("高德地理编码调用失败")
        return f"高德地图API调用失败：{e}"

    if data.get("status") != "1":
        return f"高德地理编码返回错误：{data.get('info', '未知错误')}（infocode={data.get('infocode')}）"

    geocodes = data.get("geocodes") or []
    if not geocodes:
        return f"未找到地址「{address}」对应的地理编码结果。"

    g = geocodes[0]
    location = g.get("location", "")  # "lng,lat"
    province = g.get("province", "")
    city_name = g.get("city", "") or province
    district = g.get("district", "")
    formatted = g.get("formatted_address", address)

    return (
        f"地址解析结果：\n"
        f"- 标准化地址：{formatted}\n"
        f"- 经纬度（高德GCJ02）：{location}\n"
        f"- 省份：{province}\n"
        f"- 城市：{city_name}\n"
        f"- 区县：{district}"
    )


@tool
async def amap_regeocode(longitude: str, latitude: str) -> str:
    """高德逆地理编码：把经纬度（经度,纬度）反查为结构化地址。

    参数:
        longitude: 经度（GCJ02 坐标系），例如"116.481028"
        latitude:  纬度（GCJ02 坐标系），例如"39.989643"
    """
    if not settings.amap_key:
        return "高德地图API未配置：请在 .env 中设置 AMAP_KEY。"

    base = "https://restapi.amap.com/v3/geocode/regeo"
    location = f"{longitude},{latitude}"
    params = {"key": settings.amap_key, "location": location}

    try:
        async with _make_client() as client:
            resp = await client.get(base, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.exception("高德逆地理编码调用失败")
        return f"高德地图API调用失败：{e}"

    if data.get("status") != "1":
        return f"高德逆地理编码返回错误：{data.get('info', '未知错误')}（infocode={data.get('infocode')}）"

    regeo = data.get("regeocode", {})
    addr_comp = regeo.get("addressComponent", {})
    fmt_addr = regeo.get("formatted_address", "")

    province = addr_comp.get("province", "")
    city = addr_comp.get("city", "") or province
    district = addr_comp.get("district", "")
    township = addr_comp.get("township", "")

    return (
        f"逆地理编码结果：\n"
        f"经纬度({longitude},{latitude}) 对应地址：{fmt_addr}\n"
        f"- 省份：{province}\n"
        f"- 城市：{city}\n"
        f"- 区县：{district}\n"
        f"- 乡镇/街道：{township}"
    )


@tool
async def amap_weather(city: str) -> str:
    """高德天气查询：返回指定城市的实时天气 + 未来4天预报。

    参数:
        city: 城市名或城市 adcode，例如"南京"、"320100"
    """
    if not settings.amap_key:
        return "高德地图API未配置：请在 .env 中设置 AMAP_KEY。"

    base = "https://restapi.amap.com/v3/weather/weatherInfo"
    # extensions=all 表示返回实时天气 + 预报
    params = {"key": settings.amap_key, "city": city, "extensions": "all"}

    try:
        async with _make_client() as client:
            resp = await client.get(base, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.exception("高德天气查询失败")
        return f"高德地图API调用失败：{e}"

    if data.get("status") != "1":
        return f"高德天气返回错误：{data.get('info', '未知错误')}（infocode={data.get('infocode')}）"

    lives = data.get("lives") or []
    forecasts = data.get("forecasts") or []

    lines = [f"【{city} 天气】"]

    # 实时天气
    if lives:
        live = lives[0]
        lines.append(
            f"实时：{live.get('province','')}{live.get('city','')} "
            f"{live.get('weather','')}，气温 {live.get('temperature','')}℃，"
            f"{live.get('winddirection','')}风 {live.get('windpower','')}级，"
            f"空气湿度 {live.get('humidity','')}%"
        )

    # 未来预报
    if forecasts:
        cast = forecasts[0].get("casts", [])
        lines.append("未来预报：")
        for c in cast:
            lines.append(
                f"  {c.get('date','')}（周{c.get('week','')}）："
                f"白天{c.get('dayweather','')} {c.get('daytemp','')}℃ / "
                f"夜间{c.get('nightweather','')} {c.get('nighttemp','')}℃，"
                f"{c.get('daywind','')}风{c.get('daypower','')}级"
            )

    if len(lines) == 1:
        return f"未查询到城市「{city}」的天气数据。"

    return "\n".join(lines)


@tool
async def amap_around_search(keyword: str, location: str, radius: int = 3000) -> str:
    """高德周边 POI 搜索：在给定经纬度周围指定半径内搜索关键词兴趣点。
    【重要】调用本工具前，必须先用 amap_geocode 把地名解析成经纬度，
    再把这个经纬度**原样**作为 location 传入。不要自己编造坐标。

    参数:
        keyword: 搜索关键词，如"餐厅"、"加油站"、"地铁站"
        location: 中心经纬度（必填），格式 "经度,纬度"，
                  例如 amap_geocode 返回的 "113.361597,23.124817"
        radius: 搜索半径（米），默认 3000，最大 50000
    """
    if not settings.amap_key:
        return "高德地图API未配置：请在 .env 中设置 AMAP_KEY。"

    base = "https://restapi.amap.com/v3/place/around"
    params = {
        "key": settings.amap_key,
        "keywords": keyword,
        "location": location,
        "radius": radius,
        "offset": 10,
        "page": 1,
        "extensions": "base",
    }

    try:
        async with _make_client() as client:
            resp = await client.get(base, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.exception("高德周边搜索失败")
        return f"高德地图API调用失败：{e}"

    if data.get("status") != "1":
        return f"高德周边搜索返回错误：{data.get('info', '未知错误')}（infocode={data.get('infocode')}）"

    pois = data.get("pois") or []
    if not pois:
        return f"在 {location} 周围 {radius} 米内未找到「{keyword}」相关 POI。"

    lines = [f"在 {location} 周围 {radius} 米内找到 {data.get('count', len(pois))} 个「{keyword}」："]
    for i, p in enumerate(pois[:10], 1):
        lines.append(
            f"{i}. {p.get('name','')}  |  类型：{p.get('type','')}  |  "
            f"地址：{p.get('address','-')}  |  距离：{p.get('distance','-')}米"
        )
    return "\n".join(lines)


# ============================================================
# 百度地图工具（需要 SN 签名）
# ============================================================
def _baidu_sn_sign(path: str, params: dict) -> str:
    """百度地图服务端 SN 签名算法（MD5）。

    算法步骤（百度开放平台官方文档）：
    1. 取所有请求参数（ak 保留，sn 本身不参与签名），按 key 字典序升序排序；
    2. 拼接成待签名 URL 路径串：{path}?{k1}={v1}&{k2}={v2}...（不做 urlencode，
       值直接拼接；若值含特殊字符应在调用前自行编码）；
    3. 在串末尾直接拼接 SK（service 端的 secret key），中间无任何分隔符；
    4. 对整串做 MD5 取摘要（十六进制小写），即为 sn。

    示例：path="/geocoder/v2/"，params={"address":"南京","output":"json","ak":"xxx"}
          sk="your_sk"
    待签名字符串 = "/geocoder/v2/?address=南京&ak=xxx&output=json" + "your_sk"
    sn = md5(该字符串).hexdigest()
    """
    # 1. 按 key 字典序排序（lambda kv: kv[0] 表示按元组第一个元素即 key 排序）
    sorted_items = sorted(params.items(), key=lambda kv: kv[0])
    # 2. 拼接 query string（不 urlencode，与官方签名口径一致）
    query = "&".join(f"{k}={v}" for k, v in sorted_items)
    string_to_sign = f"{path}?{query}{settings.baidu_map_sk}"
    # 4. MD5 摘要（hexdigest 返回 32 位十六进制小写字符串）
    return hashlib.md5(string_to_sign.encode("utf-8")).hexdigest()


@tool
async def baidu_geocode(address: str) -> str:
    """百度地理编码：把地址文本转换为百度墨卡托/经纬度坐标（BD09LL）。

    参数:
        address: 待解析地址，例如"南京市玄武区玄武湖公园"
    """
    if not settings.baidu_map_ak or not settings.baidu_map_sk:
        return "百度地图API未配置：请在 .env 中设置 BAIDU_MAP_AK / BAIDU_MAP_SK。"

    path = "/geocoder/v2/"
    host = "https://api.map.baidu.com"
    # 签名参与参数（不含 sn 自身）
    params = {
        "address": address,
        "output": "json",
        "ak": settings.baidu_map_ak,
    }
    sn = _baidu_sn_sign(path, params)
    params["sn"] = sn

    try:
        async with _make_client() as client:
            resp = await client.get(host + path, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.exception("百度地理编码调用失败")
        return f"百度地图API调用失败：{e}"

    if data.get("status") != 0:
        return f"百度地理编码返回错误：status={data.get('status')}，message={data.get('message', '未知错误')}"

    result = data.get("result", {})
    location = result.get("location", {})
    lng = location.get("lng", "")
    lat = location.get("lat", "")
    precise = result.get("precise", "")
    confidence = result.get("confidence", "")

    return (
        f"百度地理编码结果（BD09LL 坐标系）：\n"
        f"- 地址：{address}\n"
        f"- 经度：{lng}\n"
        f"- 纬度：{lat}\n"
        f"- 精确度：{precise}（confidence={confidence}）"
    )


@tool
async def baidu_weather(district_id: str) -> str:
    """百度天气查询：根据区县行政区划编码（adcode）查询天气。

    参数:
        district_id: 百度行政区划编码（adcode），例如南京玄武区为"320102"
    """
    if not settings.baidu_map_ak or not settings.baidu_map_sk:
        return "百度地图API未配置：请在 .env 中设置 BAIDU_MAP_AK / BAIDU_MAP_SK。"

    path = "/weather/v1/"
    host = "https://api.map.baidu.com"
    params = {
        "district_id": district_id,
        "data_type": "all",   # all = 实时 + 未来预报
        "ak": settings.baidu_map_ak,
    }
    sn = _baidu_sn_sign(path, params)
    params["sn"] = sn

    try:
        async with _make_client() as client:
            resp = await client.get(host + path, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.exception("百度天气查询失败")
        return f"百度地图API调用失败：{e}"

    if data.get("status") != 0:
        return f"百度天气返回错误：status={data.get('status')}，message={data.get('message', '未知错误')}"

    result = data.get("result", {})
    location = result.get("location", {})
    realtime = result.get("realtime", {})
    forecasts = result.get("forecasts", [])

    lines = [f"【百度天气 - {location.get('province','')}{location.get('city','')} {location.get('name','')}】"]

    if realtime:
        lines.append(
            f"实时：{realtime.get('text','')}，气温 {realtime.get('temp','')}℃，"
            f"{realtime.get('wind_direction','')}风 {realtime.get('wind_power','')}级，"
            f"湿度 {realtime.get('rh','')}%"
        )

    if forecasts:
        lines.append("预报：")
        for f in forecasts[:5]:
            lines.append(
                f"  {f.get('date','')}：{f.get('text_day','')} / {f.get('text_night','')}，"
                f"{f.get('low_temp','')}℃ ~ {f.get('high_temp','')}℃"
            )

    if len(lines) == 1:
        return f"未查询到 district_id={district_id} 的天气数据。"

    return "\n".join(lines)


# 导出所有工具，供 dynamic_tools 按名查找
__all__ = [
    "amap_geocode",
    "amap_regeocode",
    "amap_weather",
    "amap_around_search",
    "baidu_geocode",
    "baidu_weather",
]
