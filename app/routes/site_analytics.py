"""
站点统计路由模块。

本模块提供网站访问统计和用户行为追踪功能，包括：
1. 数据埋点写入
2. 事件清洗
3. 地域和设备归类
4. 统计报表输出

主要功能：
1. 数据采集
   - 页面浏览事件
   - 自定义事件追踪
   - 会话结束事件
   - 事件批次处理

2. 数据清洗
   - 事件名称长度限制
   - 文本内容限制
   - 路径长度限制
   - 事件类型白名单

3. 用户归类
   - IP地域识别
   - 设备类型检测
   - 浏览器识别
   - 操作系统识别

4. 转化追踪
   - 联系表单提交
   - 简历投递
   - 询价请求
   - Demo申请
   - 文件下载
   - 电话点击
   - 邮箱点击

5. 统计报表
   - 访问趋势
   - 热门页面
   - 用户地域分布
   - 转化漏斗
   - 实时访客

6. 数据导出
   - JSON格式导出
   - 分页查询
   - 数据聚合

作者：元芯传感技术团队
"""

import hashlib
import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from flask import jsonify, request

SITE_ANALYTICS_LOG_FILE = Path(__file__).resolve().parents[2] / 'data' / 'site_analytics_events.jsonl'
SITE_ANALYTICS_LOCK = threading.Lock()
BEIJING_TZ = timezone(timedelta(hours=8))


def _fallback_resolve_ip_location(_ip: str) -> str:
    return 'unknown'


_resolve_ip_location_fn = _fallback_resolve_ip_location

SITE_ANALYTICS_MAX_BATCH_SIZE = 25
SITE_ANALYTICS_MAX_EVENT_NAME_LENGTH = 80
SITE_ANALYTICS_MAX_TEXT_LENGTH = 300
SITE_ANALYTICS_MAX_PATH_LENGTH = 260
SITE_ANALYTICS_ALLOWED_EVENT_TYPES = {'pageview', 'event', 'session_end'}
SITE_ANALYTICS_CONVERSION_EVENTS = {
    'contact_submit',
    'job_apply',
    'quote_request',
    'request_demo',
    'download_brochure',
    'phone_click',
    'email_click',
    'form_submit',
    'demo_form',
    'quote_form',
    'contact_form',
    'job_form',
    'checkout',
    'subscribe',
    'register',
    'feedback',
    'survey',
    'review',
    'wishlist',
    'video_complete',
}
SITE_ANALYTICS_SEARCH_HOST_KEYWORDS = (
    'google.',
    'bing.',
    'baidu.',
    'yahoo.',
    'yandex.',
    'duckduckgo.',
    'sogou.',
    'so.com',
)
SITE_ANALYTICS_SOCIAL_HOST_KEYWORDS = (
    'facebook.',
    'instagram.',
    'linkedin.',
    'reddit.',
    'twitter.',
    'x.com',
    't.co',
    'weibo.',
    'zhihu.',
)


def _analytics_clean_text(value, max_length=SITE_ANALYTICS_MAX_TEXT_LENGTH):
    text = str(value or '').strip()
    if not text:
        return ''
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text[:max_length]


def _analytics_clean_id(value, max_length=64):
    text = _analytics_clean_text(value, max_length=max_length)
    if not text:
        return ''
    return re.sub(r'[^a-zA-Z0-9._:-]', '', text)[:max_length]


def _analytics_extract_host(raw_url: str) -> str:
    text = _analytics_clean_text(raw_url, max_length=SITE_ANALYTICS_MAX_TEXT_LENGTH)
    if not text:
        return ''
    try:
        parsed = urlparse(text)
    except Exception:
        return ''
    host = (parsed.netloc or '').strip().lower()
    if host.startswith('www.'):
        host = host[4:]
    return host


def _analytics_normalize_path(raw_value: str) -> str:
    text = _analytics_clean_text(raw_value, max_length=SITE_ANALYTICS_MAX_PATH_LENGTH)
    if not text:
        return '/'
    try:
        parsed = urlparse(text)
        if parsed.scheme and parsed.netloc:
            text = parsed.path or '/'
    except Exception:
        pass
    if not text.startswith('/'):
        text = f'/{text.lstrip("./")}'
    text = re.sub(r'/+', '/', text)
    return text[:SITE_ANALYTICS_MAX_PATH_LENGTH] or '/'


def _analytics_classify_device(user_agent: str) -> str:
    ua = str(user_agent or '').lower()
    if not ua:
        return 'unknown'
    tablet_keywords = ('ipad', 'tablet', 'kindle', 'playbook', 'sm-t', 'nexus 7', 'nexus 10')
    mobile_keywords = ('mobile', 'android', 'iphone', 'ipod', 'windows phone', 'blackberry', 'opera mini')
    if any(keyword in ua for keyword in tablet_keywords):
        return 'tablet'
    if any(keyword in ua for keyword in mobile_keywords):
        return 'mobile'
    return 'desktop'


def _analytics_classify_os(user_agent: str) -> str:
    ua = str(user_agent or '').lower()
    if not ua:
        return 'unknown'
    if 'harmonyos' in ua or 'hongmeng' in ua or 'hmos' in ua:
        return 'harmonyos'
    if 'windows nt' in ua or 'win64' in ua or 'wow64' in ua:
        return 'windows'
    if 'android' in ua:
        return 'android'
    if 'iphone' in ua or 'ipad' in ua or 'ipod' in ua or 'cpu iphone os' in ua or 'cpu os' in ua:
        return 'ios'
    if 'mac os x' in ua or 'macintosh' in ua:
        return 'macos'
    if 'linux' in ua:
        return 'linux'
    return 'unknown'


_ANALYTICS_CHINA_PROVINCE_ALIASES = (
    ('北京市', ('北京', '北京市', 'beijing', 'peking')),
    ('上海市', ('上海', '上海市', 'shanghai')),
    ('天津市', ('天津', '天津市', 'tianjin')),
    ('重庆市', ('重庆', '重庆市', 'chongqing')),
    ('河北省', ('河北', '河北省', 'hebei')),
    ('山西省', ('山西', '山西省', 'shanxi')),
    ('辽宁省', ('辽宁', '辽宁省', 'liaoning')),
    ('吉林省', ('吉林', '吉林省', 'jilin')),
    ('黑龙江省', ('黑龙江', '黑龙江省', 'heilongjiang')),
    ('江苏省', ('江苏', '江苏省', 'jiangsu')),
    ('浙江省', ('浙江', '浙江省', 'zhejiang')),
    ('安徽省', ('安徽', '安徽省', 'anhui')),
    ('福建省', ('福建', '福建省', 'fujian')),
    ('江西省', ('江西', '江西省', 'jiangxi')),
    ('山东省', ('山东', '山东省', 'shandong')),
    ('河南省', ('河南', '河南省', 'henan')),
    ('湖北省', ('湖北', '湖北省', 'hubei')),
    ('湖南省', ('湖南', '湖南省', 'hunan')),
    ('广东省', ('广东', '广东省', 'guangdong')),
    ('海南省', ('海南', '海南省', 'hainan')),
    ('四川省', ('四川', '四川省', 'sichuan')),
    ('贵州省', ('贵州', '贵州省', 'guizhou')),
    ('云南省', ('云南', '云南省', 'yunnan')),
    ('陕西省', ('陕西', '陕西省', 'shaanxi')),
    ('甘肃省', ('甘肃', '甘肃省', 'gansu')),
    ('青海省', ('青海', '青海省', 'qinghai')),
    ('台湾省', ('台湾', '台湾省', 'taiwan')),
    ('内蒙古自治区', ('内蒙古', '内蒙古自治区', 'inner mongolia', 'nei mongol')),
    ('广西壮族自治区', ('广西', '广西壮族自治区', 'guangxi', 'guangxi zhuang autonomous region')),
    ('西藏自治区', ('西藏', '西藏自治区', 'tibet', 'xizang', 'tibet autonomous region')),
    ('宁夏回族自治区', ('宁夏', '宁夏回族自治区', 'ningxia', 'ningxia hui autonomous region')),
    ('新疆维吾尔自治区', ('新疆', '新疆维吾尔自治区', 'xinjiang', 'xinjiang uygur autonomous region')),
    ('香港特别行政区', ('香港', '香港特别行政区', 'hong kong', 'hong kong sar', 'hong kong special administrative region', 'hongkong')),
    ('澳门特别行政区', ('澳门', '澳门特别行政区', 'macau', 'macao', 'macao sar', 'macao special administrative region')),
)


def _analytics_normalize_ascii_words(text: str) -> str:
    compact = re.sub(r'[^a-z]+', ' ', str(text or '').lower())
    compact = re.sub(r'\s+', ' ', compact).strip()
    return f' {compact} ' if compact else ''


def _analytics_build_geo_lookup_key(text: str) -> str:
    raw = str(text or '').strip().lower()
    if not raw:
        return ''
    if re.search(r'[a-z]', raw):
        return _analytics_normalize_ascii_words(raw).strip()
    return re.sub(r'[\s/|,_\-·，、()（）]+', '', raw)


_ANALYTICS_GEO_ASCII_ADMIN_SUFFIXES = (
    ('special', 'administrative', 'region'),
    ('autonomous', 'region'),
    ('municipality',),
    ('province',),
    ('city',),
    ('region',),
    ('sar',),
)


def _analytics_build_geo_match_key(text: str) -> str:
    raw = str(text or '').strip()
    if not raw:
        return ''
    if re.search(r'[A-Za-z]', raw):
        words = re.sub(r'[^a-z]+', ' ', raw.lower()).split()
        while words:
            trimmed = False
            for suffix_words in _ANALYTICS_GEO_ASCII_ADMIN_SUFFIXES:
                suffix_len = len(suffix_words)
                if suffix_len and tuple(words[-suffix_len:]) == suffix_words:
                    words = words[:-suffix_len]
                    trimmed = True
                    break
            if not trimmed:
                break
        return ' '.join(words)
    return re.sub(r'[\s/|,_\-·，、()（）]+', '', raw)


_ANALYTICS_NON_GEO_LOCATION_LABELS = {
    '未知',
    'unknown',
    'n/a',
    '-',
    '本机回环地址',
    '内网地址',
    '未指定地址',
    '保留地址',
    '组播地址',
}

_ANALYTICS_CONTINENT_LABELS = {
    'asia': '亚洲',
    'europe': '欧洲',
    'north-america': '北美洲',
    'south-america': '南美洲',
    'africa': '非洲',
    'oceania': '大洋洲',
}

_ANALYTICS_CHINA_COUNTRY_ALIASES = (
    '中国',
    '中华人民共和国',
    '中国大陆',
    'china',
    'cn',
    'prc',
    "people's republic of china",
    'people s republic of china',
    'mainland china',
    'china mainland',
)

_ANALYTICS_COUNTRY_CONTINENT_ALIASES = {
    'asia': (
        '中国', 'china',
        '日本', 'japan',
        '韩国', '南韩', '大韩民国', 'south korea', 'republic of korea', 'korea',
        '朝鲜', 'north korea', 'democratic people s republic of korea',
        '蒙古', 'mongolia',
        '新加坡', 'singapore',
        '马来西亚', 'malaysia',
        '泰国', 'thailand',
        '越南', 'vietnam',
        '印度尼西亚', '印尼', 'indonesia',
        '菲律宾', 'philippines',
        '印度', 'india',
        '巴基斯坦', 'pakistan',
        '孟加拉国', 'bangladesh',
        '斯里兰卡', 'sri lanka',
        '尼泊尔', 'nepal',
        '不丹', 'bhutan',
        '缅甸', 'myanmar',
        '老挝', 'laos',
        '柬埔寨', 'cambodia',
        '文莱', 'brunei',
        '东帝汶', 'timor leste',
        '哈萨克斯坦', 'kazakhstan',
        '乌兹别克斯坦', 'uzbekistan',
        '吉尔吉斯斯坦', 'kyrgyzstan',
        '塔吉克斯坦', 'tajikistan',
        '土库曼斯坦', 'turkmenistan',
        '阿富汗', 'afghanistan',
        '伊朗', 'iran',
        '伊拉克', 'iraq',
        '沙特阿拉伯', 'saudi arabia',
        '阿联酋', '阿拉伯联合酋长国', 'united arab emirates', 'uae',
        '卡塔尔', 'qatar',
        '科威特', 'kuwait',
        '巴林', 'bahrain',
        '阿曼', 'oman',
        '也门', 'yemen',
        '约旦', 'jordan',
        '黎巴嫩', 'lebanon',
        '叙利亚', 'syria',
        '以色列', 'israel',
        '巴勒斯坦', 'palestine',
        '土耳其', 'turkey',
        '格鲁吉亚', 'georgia',
        '亚美尼亚', 'armenia',
        '阿塞拜疆', 'azerbaijan',
        '塞浦路斯', 'cyprus',
        '马尔代夫', 'maldives',
    ),
    'europe': (
        '英国', '英格兰', '大不列颠', '联合王国', 'united kingdom', 'uk', 'britain', 'great britain', 'england',
        '爱尔兰', 'ireland',
        '法国', 'france',
        '德国', 'germany',
        '荷兰', '尼德兰', 'netherlands', 'holland',
        '比利时', 'belgium',
        '卢森堡', 'luxembourg',
        '瑞士', 'switzerland',
        '奥地利', 'austria',
        '意大利', 'italy',
        '西班牙', 'spain',
        '葡萄牙', 'portugal',
        '丹麦', 'denmark',
        '挪威', 'norway',
        '瑞典', 'sweden',
        '芬兰', 'finland',
        '冰岛', 'iceland',
        '波兰', 'poland',
        '捷克', '捷克共和国', 'czechia', 'czech republic',
        '斯洛伐克', 'slovakia',
        '匈牙利', 'hungary',
        '罗马尼亚', 'romania',
        '保加利亚', 'bulgaria',
        '希腊', 'greece',
        '克罗地亚', 'croatia',
        '斯洛文尼亚', 'slovenia',
        '塞尔维亚', 'serbia',
        '波斯尼亚和黑塞哥维那', '波黑', 'bosnia and herzegovina',
        '黑山', 'montenegro',
        '北马其顿', 'north macedonia',
        '阿尔巴尼亚', 'albania',
        '摩尔多瓦', 'moldova',
        '乌克兰', 'ukraine',
        '白俄罗斯', 'belarus',
        '立陶宛', 'lithuania',
        '拉脱维亚', 'latvia',
        '爱沙尼亚', 'estonia',
        '俄罗斯', 'russia', 'russian federation',
    ),
    'north-america': (
        '美国', '美利坚合众国', 'united states', 'united states of america', 'usa',
        '加拿大', 'canada',
        '墨西哥', 'mexico',
        '格陵兰', 'greenland',
        '古巴', 'cuba',
        '多米尼加共和国', 'dominican republic',
        '海地', 'haiti',
        '牙买加', 'jamaica',
        '危地马拉', 'guatemala',
        '伯利兹', 'belize',
        '洪都拉斯', 'honduras',
        '萨尔瓦多', 'el salvador',
        '尼加拉瓜', 'nicaragua',
        '哥斯达黎加', 'costa rica',
        '巴拿马', 'panama',
        '巴哈马', 'bahamas',
        '特立尼达和多巴哥', 'trinidad and tobago',
        '巴巴多斯', 'barbados',
        '波多黎各', 'puerto rico',
    ),
    'south-america': (
        '巴西', 'brazil',
        '阿根廷', 'argentina',
        '智利', 'chile',
        '秘鲁', 'peru',
        '哥伦比亚', 'colombia',
        '委内瑞拉', 'venezuela',
        '厄瓜多尔', 'ecuador',
        '玻利维亚', 'bolivia',
        '巴拉圭', 'paraguay',
        '乌拉圭', 'uruguay',
        '圭亚那', 'guyana',
        '苏里南', 'suriname',
        '法属圭亚那', 'french guiana',
    ),
    'africa': (
        '南非', 'south africa',
        '埃及', 'egypt',
        '尼日利亚', 'nigeria',
        '肯尼亚', 'kenya',
        '埃塞俄比亚', 'ethiopia',
        '坦桑尼亚', 'tanzania',
        '阿尔及利亚', 'algeria',
        '摩洛哥', 'morocco',
        '突尼斯', 'tunisia',
        '利比亚', 'libya',
        '苏丹', 'sudan',
        '南苏丹', 'south sudan',
        '加纳', 'ghana',
        '乌干达', 'uganda',
        '安哥拉', 'angola',
        '喀麦隆', 'cameroon',
        '科特迪瓦', '象牙海岸', 'cote d ivoire', 'ivory coast',
        '塞内加尔', 'senegal',
        '津巴布韦', 'zimbabwe',
        '赞比亚', 'zambia',
        '博茨瓦纳', 'botswana',
        '纳米比亚', 'namibia',
        '莫桑比克', 'mozambique',
        '马达加斯加', 'madagascar',
        '毛里求斯', 'mauritius',
        '卢旺达', 'rwanda',
        '刚果', 'congo',
        '刚果民主共和国', '民主刚果', 'democratic republic of the congo', 'dr congo',
        '加蓬', 'gabon',
    ),
    'oceania': (
        '澳大利亚', 'australia',
        '新西兰', 'new zealand',
        '巴布亚新几内亚', 'papua new guinea',
        '斐济', 'fiji',
        '萨摩亚', 'samoa',
        '汤加', 'tonga',
        '所罗门群岛', 'solomon islands',
        '瓦努阿图', 'vanuatu',
        '密克罗尼西亚', 'micronesia',
        '关岛', 'guam',
        '新喀里多尼亚', 'new caledonia',
    ),
}

_ANALYTICS_COUNTRY_TO_CONTINENT = {}
for _continent_key, _aliases in _ANALYTICS_COUNTRY_CONTINENT_ALIASES.items():
    for _alias in _aliases:
        _lookup_key = _analytics_build_geo_lookup_key(_alias)
        if _lookup_key:
            _ANALYTICS_COUNTRY_TO_CONTINENT[_lookup_key] = _continent_key


_ANALYTICS_CHINA_COUNTRY_LOOKUP_KEYS = {
    _analytics_build_geo_match_key(alias)
    for alias in _ANALYTICS_CHINA_COUNTRY_ALIASES
    if _analytics_build_geo_match_key(alias)
}

_ANALYTICS_CHINA_PROVINCE_LOOKUP = {}
for _province_name, _aliases in _ANALYTICS_CHINA_PROVINCE_ALIASES:
    for _alias in _aliases:
        _lookup_key = _analytics_build_geo_match_key(_alias)
        if _lookup_key:
            _ANALYTICS_CHINA_PROVINCE_LOOKUP[_lookup_key] = _province_name


def _analytics_split_location_segments(location_text: str) -> list[str]:
    text = str(location_text or '').strip()
    if not text or text in _ANALYTICS_NON_GEO_LOCATION_LABELS:
        return []
    return [segment.strip() for segment in re.split(r'\s*/\s*', text) if segment and segment.strip()]


def _analytics_match_china_province_segment(segment_text: str) -> str:
    lookup_key = _analytics_build_geo_match_key(segment_text)
    if not lookup_key:
        return ''
    return _ANALYTICS_CHINA_PROVINCE_LOOKUP.get(lookup_key, '')


def _analytics_is_china_country_segment(segment_text: str) -> bool:
    lookup_key = _analytics_build_geo_match_key(segment_text)
    if not lookup_key:
        return False
    return (
        lookup_key in _ANALYTICS_CHINA_COUNTRY_LOOKUP_KEYS
        or lookup_key in _ANALYTICS_CHINA_PROVINCE_LOOKUP
    )


def _analytics_extract_location_country_segment(location_text: str) -> str:
    segments = _analytics_split_location_segments(location_text)
    if not segments:
        return ''
    return segments[0]


def _analytics_extract_china_province(location_text: str) -> str:
    segments = _analytics_split_location_segments(location_text)
    if not segments:
        return ''

    first_segment = segments[0]
    first_lookup_key = _analytics_build_geo_match_key(first_segment)
    first_province = _analytics_match_china_province_segment(first_segment)
    if first_province and first_lookup_key not in _ANALYTICS_CHINA_COUNTRY_LOOKUP_KEYS:
        return first_province

    if not _analytics_is_china_country_segment(first_segment):
        return ''

    for segment in segments[1:3]:
        province_name = _analytics_match_china_province_segment(segment)
        if province_name:
            return province_name
    return ''


def _analytics_extract_record_province(item) -> str:
    location = _analytics_clean_text(item.get('location'), max_length=SITE_ANALYTICS_MAX_TEXT_LENGTH)
    derived_country = _analytics_extract_country_from_location(location)
    derived_province = _analytics_extract_china_province(location)
    if derived_province:
        return _analytics_clean_text(derived_province, max_length=32)
    if derived_country and derived_country != '中国':
        return ''
    province = _analytics_clean_text(item.get('province'), max_length=32)
    if province:
        return province
    return ''


def _analytics_extract_country_from_location(location_text: str) -> str:
    first_segment = _analytics_extract_location_country_segment(location_text)
    if not first_segment:
        return ''
    if _analytics_is_china_country_segment(first_segment):
        return '中国'
    return first_segment


def _analytics_extract_record_country(item) -> str:
    location = _analytics_clean_text(item.get('location'), max_length=SITE_ANALYTICS_MAX_TEXT_LENGTH)
    derived_country = _analytics_extract_country_from_location(location)
    if derived_country:
        return _analytics_clean_text(derived_country, max_length=64)
    country = _analytics_clean_text(item.get('country'), max_length=64)
    if country:
        if _analytics_is_china_country_segment(country):
            return '中国'
        return country
    return ''


def _analytics_resolve_continent_from_country(country_text: str) -> str:
    lookup_key = _analytics_build_geo_lookup_key(country_text)
    if not lookup_key:
        return ''
    return _ANALYTICS_COUNTRY_TO_CONTINENT.get(lookup_key, '')


def _analytics_resolve_visit_geo(ip_text: str):
    ip_value = str(ip_text or '').strip()
    if not ip_value:
        return {
            'ip': '',
            'location': '未知',
            'province': '',
            'country': '',
            'is_china': False,
        }
    location = _resolve_ip_location_fn(ip_value)
    province = _analytics_extract_china_province(location)
    is_china = bool(province)
    country = '中国' if is_china else _analytics_extract_country_from_location(location)
    return {
        'ip': ip_value,
        'location': location or '未知',
        'province': province,
        'country': country,
        'is_china': is_china,
    }


def _analytics_classify_source(referrer: str, utm_source: str, utm_medium: str, current_host: str) -> str:
    source = _analytics_clean_text(utm_source, max_length=64).lower()
    medium = _analytics_clean_text(utm_medium, max_length=64).lower()
    if source or medium:
        if 'social' in medium or source in {'facebook', 'instagram', 'linkedin', 'twitter', 'x', 'weibo', 'zhihu'}:
            return 'social'
        if medium in {'cpc', 'ppc', 'paid', 'paidsearch', 'sem'}:
            return 'paid'
        if medium in {'email', 'newsletter', 'edm'}:
            return 'email'
        if medium in {'affiliate'}:
            return 'affiliate'
        if medium in {'display', 'banner'}:
            return 'display'
        if medium in {'organic', 'seo'}:
            return 'search'
        return 'campaign'

    host = _analytics_extract_host(referrer)
    if not host:
        return 'direct'

    base_host = str(current_host or '').split(':', 1)[0].strip().lower()
    if base_host and (host == base_host or host.endswith(f'.{base_host}')):
        return 'internal'
    if any(keyword in host for keyword in SITE_ANALYTICS_SEARCH_HOST_KEYWORDS):
        return 'search'
    if any(keyword in host for keyword in SITE_ANALYTICS_SOCIAL_HOST_KEYWORDS):
        return 'social'
    return 'referral'


def _analytics_is_conversion_event(event_name: str) -> bool:
    name = _analytics_clean_text(event_name, max_length=SITE_ANALYTICS_MAX_EVENT_NAME_LENGTH).lower()
    if not name:
        return False
    if name in SITE_ANALYTICS_CONVERSION_EVENTS:
        return True
    if name.startswith('conversion_'):
        return True
    return False


def _analytics_is_conversion_page(page_path: str) -> bool:
    path = _analytics_normalize_path(page_path).lower()
    markers = ('/thank-you', '/thanks', '/success', '/submitted', '/done')
    return any(marker in path for marker in markers)


def _analytics_build_fallback_visitor_id(ip_text: str, user_agent: str) -> str:
    payload = f'{ip_text}|{user_agent}'.encode('utf-8', errors='ignore')
    return hashlib.sha256(payload).hexdigest()[:24]


def _analytics_to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _analytics_to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _analytics_day_key(ts: int) -> str:
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(BEIJING_TZ)
    return dt.strftime('%Y-%m-%d')


def _analytics_local_datetime(ts: int) -> datetime:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(BEIJING_TZ)


def _analytics_parse_local_date(raw_value):
    text = str(raw_value or '').strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        return None
    try:
        parsed = datetime.strptime(text, '%Y-%m-%d').date()
    except Exception:
        return None
    if parsed.strftime('%Y-%m-%d') != text:
        return None
    return parsed


def _analytics_format_local_date(value) -> str:
    return value.strftime('%Y-%m-%d')


def _analytics_granularity_label(granularity: str) -> str:
    label_map = {
        'year': '按年显示',
        'month': '按月显示',
        'week': '按周显示',
        'day': '按天显示',
        'hour': '按小时显示',
    }
    return label_map.get(str(granularity or '').strip().lower(), '按天显示')


def _analytics_bucket_key_for_date(local_date, granularity: str) -> str:
    granularity_key = str(granularity or '').strip().lower()
    if granularity_key == 'day':
        return local_date.strftime('%Y-%m-%d')
    if granularity_key == 'week':
        iso_info = local_date.isocalendar()
        return f'{iso_info.year}-W{iso_info.week:02d}'
    if granularity_key == 'month':
        return local_date.strftime('%Y-%m')
    if granularity_key == 'year':
        return local_date.strftime('%Y')
    raise ValueError('invalid granularity')


def _analytics_bucket_end_for_date(local_date, granularity: str):
    granularity_key = str(granularity or '').strip().lower()
    if granularity_key == 'day':
        return local_date
    if granularity_key == 'week':
        return local_date + timedelta(days=max(0, 6 - local_date.weekday()))
    if granularity_key == 'month':
        if local_date.month == 12:
            next_month = local_date.replace(year=local_date.year + 1, month=1, day=1)
        else:
            next_month = local_date.replace(month=local_date.month + 1, day=1)
        return next_month - timedelta(days=1)
    if granularity_key == 'year':
        return local_date.replace(month=12, day=31)
    raise ValueError('invalid granularity')


def _analytics_bucket_seed(label: str, bucket_start, bucket_end):
    return {
        'label': label,
        'bucket_start': _analytics_format_local_date(bucket_start),
        'bucket_end': _analytics_format_local_date(bucket_end),
        'pageviews': 0,
        'conversions': 0,
        'events': 0,
        'visitors': set(),
        'sessions': set(),
    }


def _analytics_build_range_buckets(start_date, end_date, granularity: str):
    bucket_keys = []
    buckets = {}
    cursor = start_date
    while cursor <= end_date:
        bucket_key = _analytics_bucket_key_for_date(cursor, granularity)
        bucket_end = min(_analytics_bucket_end_for_date(cursor, granularity), end_date)
        bucket_keys.append(bucket_key)
        buckets[bucket_key] = _analytics_bucket_seed(bucket_key, cursor, bucket_end)
        cursor = bucket_end + timedelta(days=1)
    return bucket_keys, buckets


def _build_site_analytics_report_from_buckets(
    *,
    since_ts: int,
    bucket_keys,
    buckets,
    resolve_bucket_key,
    range_meta,
    until_ts_exclusive=None,
):
    sessions = {}
    pages = {}
    event_counter = {}
    visitor_set = set()
    recent_events = []

    records = _iter_site_analytics_records()
    for item in records:
        ts = _analytics_to_int(item.get('ts'), default=0)
        if ts < since_ts:
            continue
        if until_ts_exclusive is not None and ts >= until_ts_exclusive:
            continue

        local_dt = _analytics_local_datetime(ts)
        bucket_key = resolve_bucket_key(ts, local_dt)
        if bucket_key not in buckets:
            continue

        event_type = _analytics_clean_text(item.get('event_type'), max_length=24).lower()
        event_name = _analytics_clean_text(item.get('event_name'), max_length=SITE_ANALYTICS_MAX_EVENT_NAME_LENGTH).lower()
        page_path = _analytics_normalize_path(item.get('page_path') or '/')
        page_title = _analytics_clean_text(item.get('page_title'), max_length=120)
        source = _analytics_clean_text(item.get('source'), max_length=32).lower() or 'direct'
        device = _analytics_clean_text(item.get('device'), max_length=32).lower() or 'unknown'
        os_name = _analytics_clean_text(item.get('os'), max_length=32).lower() or 'unknown'
        province = _analytics_extract_record_province(item)
        country = _analytics_extract_record_country(item)
        ip_addr = _analytics_clean_text(item.get('ip'), max_length=45)
        visitor_id = _analytics_clean_id(item.get('visitor_id'), max_length=64)
        session_id = _analytics_clean_id(item.get('session_id'), max_length=64)
        if not visitor_id:
            visitor_id = 'anonymous'
        if not session_id:
            session_id = f'anon_{visitor_id}_{_analytics_day_key(ts)}'

        visitor_set.add(visitor_id)
        buckets[bucket_key]['visitors'].add(visitor_id)
        buckets[bucket_key]['sessions'].add(session_id)

        sess = sessions.get(session_id)
        if not sess:
            sess = {
                'session_id': session_id,
                'visitor_id': visitor_id,
                'first_ts': ts,
                'last_ts': ts,
                'pageviews': 0,
                'conversions': 0,
                'reported_duration_sec': 0,
                'source': source,
                'device': device,
                'os': os_name,
                'province': province,
                'country': country,
                'ip': ip_addr,
            }
            sessions[session_id] = sess
        else:
            sess['first_ts'] = min(sess['first_ts'], ts)
            sess['last_ts'] = max(sess['last_ts'], ts)
            if sess.get('source') in {'', 'direct', 'internal', 'unknown'} and source not in {'', 'unknown'}:
                sess['source'] = source
            if sess.get('device') in {'', 'unknown'} and device not in {'', 'unknown'}:
                sess['device'] = device
            if sess.get('os') in {'', 'unknown'} and os_name not in {'', 'unknown'}:
                sess['os'] = os_name
            if not sess.get('province') and province:
                sess['province'] = province
            if not sess.get('country') and country:
                sess['country'] = country
            if not sess.get('ip') and ip_addr:
                sess['ip'] = ip_addr

        if event_type == 'pageview':
            sess['pageviews'] += 1
            buckets[bucket_key]['pageviews'] += 1

            page_stats = pages.get(page_path)
            if not page_stats:
                page_stats = {
                    'path': page_path,
                    'title': page_title,
                    'pageviews': 0,
                    'visitors': set(),
                    'sessions': set(),
                }
                pages[page_path] = page_stats
            page_stats['pageviews'] += 1
            page_stats['visitors'].add(visitor_id)
            page_stats['sessions'].add(session_id)
            if not page_stats.get('title') and page_title:
                page_stats['title'] = page_title

            if _analytics_is_conversion_page(page_path):
                sess['conversions'] += 1
                buckets[bucket_key]['conversions'] += 1

        elif event_type == 'event':
            buckets[bucket_key]['events'] += 1
            if event_name:
                event_counter[event_name] = event_counter.get(event_name, 0) + 1
            if _analytics_is_conversion_event(event_name):
                sess['conversions'] += 1
                buckets[bucket_key]['conversions'] += 1

        elif event_type == 'session_end':
            reported_duration = max(0, _analytics_to_int(item.get('session_duration_sec'), default=0))
            sess['reported_duration_sec'] = max(sess.get('reported_duration_sec', 0), reported_duration)

        event_label = event_name or event_type or 'event'
        recent_events.append({
            'timestamp': local_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'type': event_type or 'event',
            'name': event_label,
            'path': page_path,
            'source': source or '-',
            'device': device or '-',
        })

    recent_events = recent_events[-25:]

    tracked_sessions = [item for item in sessions.values() if int(item.get('pageviews') or 0) > 0]
    total_sessions = len(tracked_sessions)
    total_pageviews = sum(int(item.get('pageviews') or 0) for item in tracked_sessions)
    total_conversions = sum(int(item.get('conversions') or 0) for item in tracked_sessions)
    conversion_sessions = sum(1 for item in tracked_sessions if int(item.get('conversions') or 0) > 0)
    bounce_sessions = sum(1 for item in tracked_sessions if int(item.get('pageviews') or 0) <= 1)

    total_duration = 0
    for item in tracked_sessions:
        observed_duration = max(0, int(item.get('last_ts') or 0) - int(item.get('first_ts') or 0))
        reported_duration = max(0, int(item.get('reported_duration_sec') or 0))
        duration_sec = max(observed_duration, reported_duration)
        duration_sec = min(duration_sec, 12 * 3600)
        total_duration += duration_sec

    avg_session_duration_sec = (total_duration / total_sessions) if total_sessions else 0.0
    bounce_rate = (bounce_sessions * 100.0 / total_sessions) if total_sessions else 0.0
    conversion_rate = (conversion_sessions * 100.0 / total_sessions) if total_sessions else 0.0

    source_counter = {}
    device_counter = {}
    os_counter = {}
    province_counter = {}
    continent_counter = {}
    country_counter = {}
    for item in tracked_sessions:
        source = _analytics_clean_text(item.get('source'), max_length=32).lower() or 'direct'
        device = _analytics_clean_text(item.get('device'), max_length=32).lower() or 'unknown'
        os_name = _analytics_clean_text(item.get('os'), max_length=32).lower() or 'unknown'
        province = _analytics_clean_text(item.get('province'), max_length=32)
        country = _analytics_clean_text(item.get('country'), max_length=64)
        source_counter[source] = source_counter.get(source, 0) + 1
        device_counter[device] = device_counter.get(device, 0) + 1
        os_counter[os_name] = os_counter.get(os_name, 0) + 1
        if province:
            province_counter[province] = province_counter.get(province, 0) + 1
        continent_key = _analytics_resolve_continent_from_country(country)
        if country and country != '中国' and continent_key:
            continent_counter[continent_key] = continent_counter.get(continent_key, 0) + 1
        if country:
            country_counter[country] = country_counter.get(country, 0) + 1

    source_rows = [
        {
            'source': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in source_counter.items()
    ]
    source_rows.sort(key=lambda item: item['sessions'], reverse=True)

    device_rows = [
        {
            'device': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in device_counter.items()
    ]
    device_rows.sort(key=lambda item: item['sessions'], reverse=True)

    os_rows = [
        {
            'os': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in os_counter.items()
    ]
    os_rows.sort(key=lambda item: item['sessions'], reverse=True)

    province_rows = [
        {
            'province': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in province_counter.items()
    ]
    province_rows.sort(key=lambda item: item['sessions'], reverse=True)

    overseas_sessions = sum(continent_counter.values())
    continent_rows = [
        {
            'continent_key': key,
            'continent': _ANALYTICS_CONTINENT_LABELS.get(key, key),
            'sessions': value,
            'ratio': round((value * 100.0 / overseas_sessions), 2) if overseas_sessions else 0.0,
        }
        for key, value in continent_counter.items()
    ]
    continent_rows.sort(key=lambda item: item['sessions'], reverse=True)

    country_rows = [
        {
            'country': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in country_counter.items()
    ]
    country_rows.sort(key=lambda item: item['sessions'], reverse=True)

    china_map_data = [
        {
            'name': item['province'],
            'value': item['sessions'],
        }
        for item in province_rows
    ]

    top_pages = []
    for path_key, stats in pages.items():
        top_pages.append({
            'path': path_key,
            'title': stats.get('title') or '',
            'pageviews': int(stats.get('pageviews') or 0),
            'unique_visitors': len(stats.get('visitors', set())),
            'sessions': len(stats.get('sessions', set())),
        })
    top_pages.sort(key=lambda item: item['pageviews'], reverse=True)
    top_pages = top_pages[:12]

    top_events = [{'name': name, 'count': count} for name, count in event_counter.items()]
    top_events.sort(key=lambda item: item['count'], reverse=True)
    top_events = top_events[:12]

    trend = []
    for bucket_key in bucket_keys:
        row = buckets.get(bucket_key, {})
        trend.append({
            'date': str(row.get('label') or bucket_key),
            'label': str(row.get('label') or bucket_key),
            'bucket_start': str(row.get('bucket_start') or ''),
            'bucket_end': str(row.get('bucket_end') or ''),
            'pageviews': int(row.get('pageviews') or 0),
            'unique_visitors': len(row.get('visitors', set())),
            'sessions': len(row.get('sessions', set())),
            'conversions': int(row.get('conversions') or 0),
            'events': int(row.get('events') or 0),
        })

    return {
        **(range_meta or {}),
        'generated_at': datetime.now(BEIJING_TZ).isoformat(timespec='seconds'),
        'summary': {
            'pageviews': total_pageviews,
            'unique_visitors': len(visitor_set),
            'sessions': total_sessions,
            'avg_session_duration_sec': round(avg_session_duration_sec, 2),
            'bounce_rate': round(bounce_rate, 2),
            'conversion_events': total_conversions,
            'conversion_sessions': conversion_sessions,
            'conversion_rate': round(conversion_rate, 2),
        },
        'source_breakdown': source_rows,
        'device_breakdown': device_rows,
        'os_breakdown': os_rows,
        'province_breakdown': province_rows,
        'continent_breakdown': continent_rows,
        'country_breakdown': country_rows,
        'china_map_data': china_map_data,
        'top_pages': top_pages,
        'top_events': top_events,
        'trend': trend,
        'recent_events': recent_events,
    }


def _analytics_sanitize_event(raw_event, request_host: str, request_ua: str, request_ip: str):
    if not isinstance(raw_event, dict):
        return None

    event_type = _analytics_clean_text(raw_event.get('event_type') or raw_event.get('type'), max_length=24).lower()
    if event_type not in SITE_ANALYTICS_ALLOWED_EVENT_TYPES:
        return None

    page_path = _analytics_normalize_path(raw_event.get('page_path') or raw_event.get('path') or '/')
    if page_path.startswith('/admin'):
        return None

    page_title = _analytics_clean_text(raw_event.get('page_title') or raw_event.get('title'), max_length=120)
    referrer = _analytics_clean_text(raw_event.get('referrer'), max_length=SITE_ANALYTICS_MAX_TEXT_LENGTH)
    event_name = _analytics_clean_text(raw_event.get('event_name') or raw_event.get('name'), max_length=SITE_ANALYTICS_MAX_EVENT_NAME_LENGTH).lower()
    visitor_id = _analytics_clean_id(raw_event.get('visitor_id'), max_length=64)
    session_id = _analytics_clean_id(raw_event.get('session_id'), max_length=64)

    if not visitor_id:
        visitor_id = _analytics_build_fallback_visitor_id(request_ip, request_ua)
    if not session_id:
        session_id = f's_{visitor_id[:12]}'

    utm = raw_event.get('utm', {})
    utm_source = ''
    utm_medium = ''
    if isinstance(utm, dict):
        utm_source = _analytics_clean_text(utm.get('source'), max_length=64).lower()
        utm_medium = _analytics_clean_text(utm.get('medium'), max_length=64).lower()

    source = _analytics_classify_source(referrer, utm_source, utm_medium, request_host)
    device = _analytics_classify_device(request_ua)
    os_name = _analytics_classify_os(request_ua)
    geo = _analytics_resolve_visit_geo(request_ip)
    session_duration_sec = max(0, _analytics_to_int(raw_event.get('session_duration_sec'), default=0))
    scroll_depth = max(0, min(100, _analytics_to_int(raw_event.get('scroll_depth'), default=0)))
    event_value = _analytics_to_float(raw_event.get('event_value'), default=0.0)

    now_ts = int(time.time())
    return {
        'ts': now_ts,
        'day': _analytics_day_key(now_ts),
        'event_type': event_type,
        'event_name': event_name,
        'event_value': event_value,
        'page_path': page_path,
        'page_title': page_title,
        'referrer': referrer,
        'referrer_host': _analytics_extract_host(referrer),
        'source': source,
        'device': device,
        'os': os_name,
        'ip': geo.get('ip') or '',
        'location': geo.get('location') or '未知',
        'province': geo.get('province') or '',
        'country': geo.get('country') or '',
        'visitor_id': visitor_id,
        'session_id': session_id,
        'session_duration_sec': session_duration_sec,
        'scroll_depth': scroll_depth,
    }


def _append_site_analytics_records(records):
    safe_records = [item for item in (records or []) if isinstance(item, dict)]
    if not safe_records:
        return 0
    SITE_ANALYTICS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SITE_ANALYTICS_LOCK:
        with SITE_ANALYTICS_LOG_FILE.open('a', encoding='utf-8') as fp:
            for item in safe_records:
                fp.write(json.dumps(item, ensure_ascii=False, separators=(',', ':')) + '\n')
    return len(safe_records)


def _iter_site_analytics_records():
    if not SITE_ANALYTICS_LOG_FILE.exists():
        return []
    with SITE_ANALYTICS_LOCK:
        try:
            lines = SITE_ANALYTICS_LOG_FILE.read_text(encoding='utf-8').splitlines()
        except Exception:
            return []
    output = []
    for line in lines:
        row = str(line or '').strip()
        if not row:
            continue
        try:
            obj = json.loads(row)
        except Exception:
            continue
        if isinstance(obj, dict):
            output.append(obj)
    return output


def build_site_analytics_report(range_days=30):
    now_local = datetime.now(BEIJING_TZ)
    range_raw = str(range_days or '').strip().lower()
    is_last_24h = range_raw in {'24h', 'last24h', '24hour', '24hours'}

    bucket_keys = []
    buckets = {}
    range_days_value = 30
    range_key = '30d'
    range_label = '最近 30 天'

    if is_last_24h:
        range_days_value = 1
        range_key = '24h'
        range_label = '最近24小时'
        current_hour = now_local.replace(minute=0, second=0, microsecond=0)
        start_hour = current_hour - timedelta(hours=23)
        since_ts = int(start_hour.astimezone(timezone.utc).timestamp())
        for idx in range(24):
            point = start_hour + timedelta(hours=idx)
            bucket_key = point.strftime('%Y-%m-%d %H:00')
            bucket_keys.append(bucket_key)
            buckets[bucket_key] = {
                'pageviews': 0,
                'conversions': 0,
                'events': 0,
                'visitors': set(),
                'sessions': set(),
            }

        def resolve_bucket_key(ts: int) -> str:
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(BEIJING_TZ)
            return dt.strftime('%Y-%m-%d %H:00')

    else:
        try:
            days = int(range_days)
        except Exception:
            days = 30
        if days not in (7, 30, 90, 180):
            days = 30
        range_days_value = days
        range_key = f'{days}d'
        range_label = f'最近 {days} 天'

        start_date = now_local.date() - timedelta(days=days - 1)
        start_dt_local = datetime.combine(start_date, datetime.min.time(), tzinfo=BEIJING_TZ)
        since_ts = int(start_dt_local.astimezone(timezone.utc).timestamp())
        for idx in range(days):
            d = start_date + timedelta(days=idx)
            bucket_key = d.strftime('%Y-%m-%d')
            bucket_keys.append(bucket_key)
            buckets[bucket_key] = {
                'pageviews': 0,
                'conversions': 0,
                'events': 0,
                'visitors': set(),
                'sessions': set(),
            }

        def resolve_bucket_key(ts: int) -> str:
            return _analytics_day_key(ts)

    sessions = {}
    pages = {}
    event_counter = {}
    visitor_set = set()
    recent_events = []

    records = _iter_site_analytics_records()
    for item in records:
        ts = _analytics_to_int(item.get('ts'), default=0)
        if ts < since_ts:
            continue
        bucket_key = resolve_bucket_key(ts)
        if bucket_key not in buckets:
            continue

        event_type = _analytics_clean_text(item.get('event_type'), max_length=24).lower()
        event_name = _analytics_clean_text(item.get('event_name'), max_length=SITE_ANALYTICS_MAX_EVENT_NAME_LENGTH).lower()
        page_path = _analytics_normalize_path(item.get('page_path') or '/')
        page_title = _analytics_clean_text(item.get('page_title'), max_length=120)
        source = _analytics_clean_text(item.get('source'), max_length=32).lower() or 'direct'
        device = _analytics_clean_text(item.get('device'), max_length=32).lower() or 'unknown'
        os_name = _analytics_clean_text(item.get('os'), max_length=32).lower() or 'unknown'
        province = _analytics_extract_record_province(item)
        country = _analytics_extract_record_country(item)
        ip_addr = _analytics_clean_text(item.get('ip'), max_length=45)
        visitor_id = _analytics_clean_id(item.get('visitor_id'), max_length=64)
        session_id = _analytics_clean_id(item.get('session_id'), max_length=64)
        if not visitor_id:
            visitor_id = 'anonymous'
        if not session_id:
            session_id = f'anon_{visitor_id}_{_analytics_day_key(ts)}'

        visitor_set.add(visitor_id)
        buckets[bucket_key]['visitors'].add(visitor_id)
        buckets[bucket_key]['sessions'].add(session_id)

        sess = sessions.get(session_id)
        if not sess:
            sess = {
                'session_id': session_id,
                'visitor_id': visitor_id,
                'first_ts': ts,
                'last_ts': ts,
                'pageviews': 0,
                'conversions': 0,
                'reported_duration_sec': 0,
                'source': source,
                'device': device,
                'os': os_name,
                'province': province,
                'country': country,
                'ip': ip_addr,
            }
            sessions[session_id] = sess
        else:
            sess['first_ts'] = min(sess['first_ts'], ts)
            sess['last_ts'] = max(sess['last_ts'], ts)
            if sess.get('source') in {'', 'direct', 'internal', 'unknown'} and source not in {'', 'unknown'}:
                sess['source'] = source
            if sess.get('device') in {'', 'unknown'} and device not in {'', 'unknown'}:
                sess['device'] = device
            if sess.get('os') in {'', 'unknown'} and os_name not in {'', 'unknown'}:
                sess['os'] = os_name
            if not sess.get('province') and province:
                sess['province'] = province
            if not sess.get('country') and country:
                sess['country'] = country
            if not sess.get('ip') and ip_addr:
                sess['ip'] = ip_addr

        if event_type == 'pageview':
            sess['pageviews'] += 1
            buckets[bucket_key]['pageviews'] += 1

            page_stats = pages.get(page_path)
            if not page_stats:
                page_stats = {
                    'path': page_path,
                    'title': page_title,
                    'pageviews': 0,
                    'visitors': set(),
                    'sessions': set(),
                }
                pages[page_path] = page_stats
            page_stats['pageviews'] += 1
            page_stats['visitors'].add(visitor_id)
            page_stats['sessions'].add(session_id)
            if not page_stats.get('title') and page_title:
                page_stats['title'] = page_title

            if _analytics_is_conversion_page(page_path):
                sess['conversions'] += 1
                buckets[bucket_key]['conversions'] += 1

        elif event_type == 'event':
            buckets[bucket_key]['events'] += 1
            if event_name:
                event_counter[event_name] = event_counter.get(event_name, 0) + 1
            if _analytics_is_conversion_event(event_name):
                sess['conversions'] += 1
                buckets[bucket_key]['conversions'] += 1

        elif event_type == 'session_end':
            reported_duration = max(0, _analytics_to_int(item.get('session_duration_sec'), default=0))
            sess['reported_duration_sec'] = max(sess.get('reported_duration_sec', 0), reported_duration)

        event_label = event_name or event_type or 'event'
        recent_events.append({
            'timestamp': datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S'),
            'type': event_type or 'event',
            'name': event_label,
            'path': page_path,
            'source': source or '-',
            'device': device or '-',
        })

    recent_events = recent_events[-25:]

    tracked_sessions = [item for item in sessions.values() if int(item.get('pageviews') or 0) > 0]
    total_sessions = len(tracked_sessions)
    total_pageviews = sum(int(item.get('pageviews') or 0) for item in tracked_sessions)
    total_conversions = sum(int(item.get('conversions') or 0) for item in tracked_sessions)
    conversion_sessions = sum(1 for item in tracked_sessions if int(item.get('conversions') or 0) > 0)
    bounce_sessions = sum(1 for item in tracked_sessions if int(item.get('pageviews') or 0) <= 1)

    total_duration = 0
    for item in tracked_sessions:
        observed_duration = max(0, int(item.get('last_ts') or 0) - int(item.get('first_ts') or 0))
        reported_duration = max(0, int(item.get('reported_duration_sec') or 0))
        duration_sec = max(observed_duration, reported_duration)
        duration_sec = min(duration_sec, 12 * 3600)
        total_duration += duration_sec

    avg_session_duration_sec = (total_duration / total_sessions) if total_sessions else 0.0
    bounce_rate = (bounce_sessions * 100.0 / total_sessions) if total_sessions else 0.0
    conversion_rate = (conversion_sessions * 100.0 / total_sessions) if total_sessions else 0.0

    source_counter = {}
    device_counter = {}
    os_counter = {}
    province_counter = {}
    continent_counter = {}
    country_counter = {}
    for item in tracked_sessions:
        source = _analytics_clean_text(item.get('source'), max_length=32).lower() or 'direct'
        device = _analytics_clean_text(item.get('device'), max_length=32).lower() or 'unknown'
        os_name = _analytics_clean_text(item.get('os'), max_length=32).lower() or 'unknown'
        province = _analytics_clean_text(item.get('province'), max_length=32)
        country = _analytics_clean_text(item.get('country'), max_length=64)
        source_counter[source] = source_counter.get(source, 0) + 1
        device_counter[device] = device_counter.get(device, 0) + 1
        os_counter[os_name] = os_counter.get(os_name, 0) + 1
        if province:
            province_counter[province] = province_counter.get(province, 0) + 1
        continent_key = _analytics_resolve_continent_from_country(country)
        if country and country != '中国' and continent_key:
            continent_counter[continent_key] = continent_counter.get(continent_key, 0) + 1
        if country:
            country_counter[country] = country_counter.get(country, 0) + 1

    source_rows = [
        {
            'source': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in source_counter.items()
    ]
    source_rows.sort(key=lambda item: item['sessions'], reverse=True)

    device_rows = [
        {
            'device': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in device_counter.items()
    ]
    device_rows.sort(key=lambda item: item['sessions'], reverse=True)

    os_rows = [
        {
            'os': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in os_counter.items()
    ]
    os_rows.sort(key=lambda item: item['sessions'], reverse=True)

    province_rows = [
        {
            'province': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in province_counter.items()
    ]
    province_rows.sort(key=lambda item: item['sessions'], reverse=True)

    overseas_sessions = sum(continent_counter.values())
    continent_rows = [
        {
            'continent_key': key,
            'continent': _ANALYTICS_CONTINENT_LABELS.get(key, key),
            'sessions': value,
            'ratio': round((value * 100.0 / overseas_sessions), 2) if overseas_sessions else 0.0,
        }
        for key, value in continent_counter.items()
    ]
    continent_rows.sort(key=lambda item: item['sessions'], reverse=True)

    country_rows = [
        {
            'country': key,
            'sessions': value,
            'ratio': round((value * 100.0 / total_sessions), 2) if total_sessions else 0.0,
        }
        for key, value in country_counter.items()
    ]
    country_rows.sort(key=lambda item: item['sessions'], reverse=True)

    china_map_data = [
        {
            'name': item['province'],
            'value': item['sessions'],
        }
        for item in province_rows
    ]

    top_pages = []
    for path_key, stats in pages.items():
        top_pages.append({
            'path': path_key,
            'title': stats.get('title') or '',
            'pageviews': int(stats.get('pageviews') or 0),
            'unique_visitors': len(stats.get('visitors', set())),
            'sessions': len(stats.get('sessions', set())),
        })
    top_pages.sort(key=lambda item: item['pageviews'], reverse=True)
    top_pages = top_pages[:12]

    top_events = [{'name': name, 'count': count} for name, count in event_counter.items()]
    top_events.sort(key=lambda item: item['count'], reverse=True)
    top_events = top_events[:12]

    trend = []
    for bucket_key in bucket_keys:
        row = buckets.get(bucket_key, {})
        trend.append({
            'date': bucket_key,
            'pageviews': int(row.get('pageviews') or 0),
            'unique_visitors': len(row.get('visitors', set())),
            'sessions': len(row.get('sessions', set())),
            'conversions': int(row.get('conversions') or 0),
            'events': int(row.get('events') or 0),
        })

    return {
        'range_days': range_days_value,
        'range_key': range_key,
        'range_label': range_label,
        'generated_at': datetime.now(BEIJING_TZ).isoformat(timespec='seconds'),
        'summary': {
            'pageviews': total_pageviews,
            'unique_visitors': len(visitor_set),
            'sessions': total_sessions,
            'avg_session_duration_sec': round(avg_session_duration_sec, 2),
            'bounce_rate': round(bounce_rate, 2),
            'conversion_events': total_conversions,
            'conversion_sessions': conversion_sessions,
            'conversion_rate': round(conversion_rate, 2),
        },
        'source_breakdown': source_rows,
        'device_breakdown': device_rows,
        'os_breakdown': os_rows,
        'province_breakdown': province_rows,
        'continent_breakdown': continent_rows,
        'country_breakdown': country_rows,
        'china_map_data': china_map_data,
        'top_pages': top_pages,
        'top_events': top_events,
        'trend': trend,
        'recent_events': recent_events,
    }




# 路由注册入口。
def build_site_analytics_report(range_days=30, start_date=None, end_date=None, granularity='day'):
    start_date_raw = str(start_date or '').strip()
    end_date_raw = str(end_date or '').strip()
    granularity_key = str(granularity or 'day').strip().lower() or 'day'

    if start_date_raw or end_date_raw:
        if not start_date_raw or not end_date_raw:
            raise ValueError('开始日期和结束日期必须同时填写')
        if granularity_key not in {'year', 'month', 'week', 'day'}:
            raise ValueError('显示粒度无效')

        start_date_value = _analytics_parse_local_date(start_date_raw)
        end_date_value = _analytics_parse_local_date(end_date_raw)
        if not start_date_value or not end_date_value:
            raise ValueError('日期格式无效，必须为 YYYY-MM-DD')
        if start_date_value > end_date_value:
            raise ValueError('开始日期不能晚于结束日期')

        bucket_keys, buckets = _analytics_build_range_buckets(start_date_value, end_date_value, granularity_key)
        start_dt_local = datetime.combine(start_date_value, datetime.min.time(), tzinfo=BEIJING_TZ)
        end_dt_exclusive_local = datetime.combine(end_date_value + timedelta(days=1), datetime.min.time(), tzinfo=BEIJING_TZ)
        since_ts = int(start_dt_local.astimezone(timezone.utc).timestamp())
        until_ts_exclusive = int(end_dt_exclusive_local.astimezone(timezone.utc).timestamp())

        return _build_site_analytics_report_from_buckets(
            since_ts=since_ts,
            until_ts_exclusive=until_ts_exclusive,
            bucket_keys=bucket_keys,
            buckets=buckets,
            resolve_bucket_key=lambda _ts, local_dt: _analytics_bucket_key_for_date(local_dt.date(), granularity_key),
            range_meta={
                'range_key': f'{granularity_key}:{start_date_raw}:{end_date_raw}',
                'range_label': f'{start_date_raw} 至 {end_date_raw} · {_analytics_granularity_label(granularity_key)}',
                'granularity': granularity_key,
                'start_date': start_date_raw,
                'end_date': end_date_raw,
            },
        )

    now_local = datetime.now(BEIJING_TZ)
    range_raw = str(range_days or '').strip().lower()
    is_last_24h = range_raw in {'24h', 'last24h', '24hour', '24hours'}

    bucket_keys = []
    buckets = {}
    range_days_value = 30
    range_key = '30d'
    range_label = '最近 30 天'
    report_granularity = 'day'

    if is_last_24h:
        range_days_value = 1
        range_key = '24h'
        range_label = '最近24小时'
        report_granularity = 'hour'
        current_hour = now_local.replace(minute=0, second=0, microsecond=0)
        start_hour = current_hour - timedelta(hours=23)
        since_ts = int(start_hour.astimezone(timezone.utc).timestamp())
        for idx in range(24):
            point = start_hour + timedelta(hours=idx)
            bucket_key = point.strftime('%Y-%m-%d %H:00')
            bucket_keys.append(bucket_key)
            buckets[bucket_key] = {
                'label': bucket_key,
                'bucket_start': bucket_key,
                'bucket_end': bucket_key,
                'pageviews': 0,
                'conversions': 0,
                'events': 0,
                'visitors': set(),
                'sessions': set(),
            }

        def resolve_bucket_key(_ts: int, local_dt: datetime) -> str:
            return local_dt.strftime('%Y-%m-%d %H:00')

        report_start_date = start_hour.date()
        report_end_date = current_hour.date()
    else:
        try:
            days = int(range_days)
        except Exception:
            days = 30
        if days not in (7, 30, 90, 180):
            days = 30
        range_days_value = days
        range_key = f'{days}d'
        range_label = f'最近 {days} 天'

        report_start_date = now_local.date() - timedelta(days=days - 1)
        report_end_date = now_local.date()
        start_dt_local = datetime.combine(report_start_date, datetime.min.time(), tzinfo=BEIJING_TZ)
        since_ts = int(start_dt_local.astimezone(timezone.utc).timestamp())
        for idx in range(days):
            bucket_date = report_start_date + timedelta(days=idx)
            bucket_key = bucket_date.strftime('%Y-%m-%d')
            bucket_keys.append(bucket_key)
            buckets[bucket_key] = _analytics_bucket_seed(bucket_key, bucket_date, bucket_date)

        def resolve_bucket_key(_ts: int, local_dt: datetime) -> str:
            return local_dt.strftime('%Y-%m-%d')

    return _build_site_analytics_report_from_buckets(
        since_ts=since_ts,
        bucket_keys=bucket_keys,
        buckets=buckets,
        resolve_bucket_key=resolve_bucket_key,
        range_meta={
            'range_days': range_days_value,
            'range_key': range_key,
            'range_label': range_label,
            'granularity': report_granularity,
            'start_date': _analytics_format_local_date(report_start_date),
            'end_date': _analytics_format_local_date(report_end_date),
        },
    )


def register_site_analytics_routes(
    app,
    *,
    login_required,
    data_dir,
    get_client_ip,
    resolve_ip_location,
    beijing_tz,
):
    """注册公开埋点收集与后台统计报表相关路由。"""
    global SITE_ANALYTICS_LOG_FILE, BEIJING_TZ, _resolve_ip_location_fn

    SITE_ANALYTICS_LOG_FILE = Path(data_dir) / "site_analytics_events.jsonl"
    BEIJING_TZ = beijing_tz or BEIJING_TZ
    _resolve_ip_location_fn = resolve_ip_location

    @app.route('/api/analytics/collect', methods=['POST'])
    def collect_site_analytics():
        """收集公开站点的统计事件。"""
        content_len = int(request.content_length or 0)
        if content_len and content_len > 64 * 1024:
            return jsonify({'success': False, 'message': 'payload too large'}), 413

        payload = request.get_json(silent=True) or {}
        raw_events = []
        if isinstance(payload, dict) and isinstance(payload.get('events'), list):
            raw_events = payload.get('events') or []
        elif isinstance(payload, dict):
            raw_events = [payload]

        if not raw_events:
            return jsonify({'success': False, 'message': 'no events'}), 400

        request_host = str(request.host or '').split(':', 1)[0].strip().lower()
        request_ua = str(request.headers.get('User-Agent') or '').strip()
        request_ip = get_client_ip()

        records = []
        for raw in raw_events[:SITE_ANALYTICS_MAX_BATCH_SIZE]:
            item = _analytics_sanitize_event(raw, request_host=request_host, request_ua=request_ua, request_ip=request_ip)
            if item:
                records.append(item)

        accepted = _append_site_analytics_records(records)
        return jsonify({'success': True, 'accepted': accepted})


    @app.route('/api/admin/site-reports', methods=['GET'])
    @login_required
    def get_site_reports_admin():
        """获取后台仪表盘使用的站点统计报表。"""
        range_days = request.args.get('range_days', 30)
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        granularity = request.args.get('granularity', 'day')
        try:
            report = build_site_analytics_report(
                range_days=range_days,
                start_date=start_date,
                end_date=end_date,
                granularity=granularity,
            )
        except ValueError as exc:
            return jsonify({'success': False, 'message': str(exc)}), 400
        return jsonify({'success': True, **report})



