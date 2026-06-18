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

import calendar
import hashlib
import html
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from flask import current_app, jsonify, request, send_file, session

SITE_ANALYTICS_LOG_FILE = Path(__file__).resolve().parents[2] / 'data' / 'site_analytics_events.jsonl'
SITE_ANALYTICS_AI_REPORTS_FILE = Path(__file__).resolve().parents[2] / 'data' / 'site_analytics_ai_reports.jsonl'
SITE_ANALYTICS_AI_REPORTS_DIR = Path(__file__).resolve().parents[2] / 'data' / 'site_analytics_ai_reports'
SITE_ANALYTICS_AI_REPORTS_INDEX_FILE = SITE_ANALYTICS_AI_REPORTS_DIR / 'index.json'
SITE_ANALYTICS_AI_REPORTS_PDF_DIR = SITE_ANALYTICS_AI_REPORTS_DIR / 'pdf_cache'
SITE_ANALYTICS_AI_JOBS_DIR = Path(__file__).resolve().parents[2] / 'data' / 'site_analytics_ai_jobs'
SITE_ANALYTICS_AI_GENERATION_LOCK_FILE = Path(__file__).resolve().parents[2] / 'data' / 'site_analytics_ai_report_generation.lock'
SITE_ANALYTICS_AI_PDF_LOCK_FILE = Path(__file__).resolve().parents[2] / 'data' / 'site_analytics_ai_report_pdf.lock'
SITE_ANALYTICS_LOCK = threading.Lock()
SITE_ANALYTICS_AI_REPORTS_LOCK = threading.RLock()
SITE_ANALYTICS_AI_JOBS_LOCK = threading.Lock()
BEIJING_TZ = timezone(timedelta(hours=8))
LOGGER = logging.getLogger(__name__)


def _fallback_resolve_ip_location(_ip: str) -> str:
    return 'unknown'


_resolve_ip_location_fn = _fallback_resolve_ip_location
_site_report_get_config_fn = lambda: {}
_site_report_requests_support = False
_site_report_requests_module = None
_site_report_httpx_support = False
_site_report_httpx_module = None
_site_report_update_config_fn = None

SITE_ANALYTICS_MAX_BATCH_SIZE = 25
SITE_ANALYTICS_MAX_EVENT_NAME_LENGTH = 80
SITE_ANALYTICS_MAX_TEXT_LENGTH = 300
SITE_ANALYTICS_MAX_PATH_LENGTH = 260
SITE_ANALYTICS_AI_REPORTS_PER_PERIOD_LIMIT = 50
SITE_ANALYTICS_AI_JOB_LOCK_TTL_SECONDS = 20 * 60
SITE_ANALYTICS_AI_PDF_LOCK_TTL_SECONDS = 3 * 60
SITE_ANALYTICS_AI_DEFAULT_MAX_TOKENS = 2200
SITE_ANALYTICS_AI_DEFAULT_TEMPERATURE = 0.2
SITE_ANALYTICS_AI_PDF_TEMPLATE_VERSION = 'v20260613'
SITE_ANALYTICS_ALLOWED_EVENT_TYPES = {'pageview', 'event', 'session_end'}

# ── 定时报告调度相关 ──
SCHEDULED_REPORTS_DIR = Path(__file__).resolve().parents[2] / 'data' / 'scheduled_reports'
SCHEDULED_REPORTS_STATE_FILE = SCHEDULED_REPORTS_DIR / 'state.json'
SCHEDULED_REPORTS_LOCK_FILE = SCHEDULED_REPORTS_DIR / 'scheduler.lock'
SCHEDULED_REPORT_GENERATE_HOUR_BEIJING = 2  # 北京时间凌晨 2 点生成
SCHEDULED_REPORT_CHECK_INTERVAL = 600  # 10 分钟检查一次
SCHEDULED_REPORT_LOCK_TTL = 15 * 60  # 调度器文件锁 TTL 15 分钟
SCHEDULED_REPORT_MAX_FAILURES = 3  # 连续失败次数上限
_SCHEDULED_REPORT_THREAD_LOCK = threading.Lock()

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


def _analytics_add_months(value, months: int):
    month_index = (value.year * 12) + (value.month - 1) + int(months or 0)
    year = month_index // 12
    month = (month_index % 12) + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _analytics_month_end(value):
    return value.replace(day=calendar.monthrange(value.year, value.month)[1])


def _analytics_period_bounds(period: str, anchor_date):
    period_key = str(period or '').strip().lower()
    if period_key == 'week':
        start = anchor_date - timedelta(days=anchor_date.weekday())
        end = start + timedelta(days=6)
        return start, end
    if period_key == 'month':
        start = anchor_date.replace(day=1)
        return start, _analytics_month_end(anchor_date)
    if period_key == 'quarter':
        start_month = ((anchor_date.month - 1) // 3) * 3 + 1
        start = anchor_date.replace(month=start_month, day=1)
        end_month_anchor = _analytics_add_months(start, 2)
        return start, _analytics_month_end(end_month_anchor)
    if period_key == 'year':
        return anchor_date.replace(month=1, day=1), anchor_date.replace(month=12, day=31)
    raise ValueError('报告周期无效')


def _analytics_previous_period_bounds(period: str, current_start, current_end):
    period_key = str(period or '').strip().lower()
    if period_key == 'week':
        return current_start - timedelta(days=7), current_end - timedelta(days=7)
    if period_key == 'month':
        previous_anchor = current_start - timedelta(days=1)
        start = previous_anchor.replace(day=1)
        return start, _analytics_month_end(previous_anchor)
    if period_key == 'quarter':
        start = _analytics_add_months(current_start, -3)
        end = current_start - timedelta(days=1)
        return start, end
    if period_key == 'year':
        return current_start.replace(year=current_start.year - 1), current_end.replace(year=current_end.year - 1)
    raise ValueError('报告周期无效')


def _analytics_report_period_label(period: str) -> str:
    label_map = {
        'week': '周报',
        'month': '月报',
        'quarter': '季报',
        'year': '年报',
    }
    return label_map.get(str(period or '').strip().lower(), '运营报告')


def _analytics_report_period_granularity(period: str) -> str:
    return {
        'week': 'day',
        'month': 'day',
        'quarter': 'week',
        'year': 'month',
    }.get(str(period or '').strip().lower(), 'day')


def _analytics_granularity_label(granularity: str) -> str:
    label_map = {
        'year': '按年显示',
        'quarter': '按季度显示',
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
    if granularity_key == 'quarter':
        quarter = ((local_date.month - 1) // 3) + 1
        return f'{local_date.year}-Q{quarter}'
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
    if granularity_key == 'quarter':
        quarter_start_month = ((local_date.month - 1) // 3) * 3 + 1
        if quarter_start_month == 10:
            next_quarter = local_date.replace(year=local_date.year + 1, month=1, day=1)
        else:
            next_quarter = local_date.replace(month=quarter_start_month + 3, day=1)
        return next_quarter - timedelta(days=1)
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


def _analytics_report_safe_id(value: str) -> str:
    text = str(value or '').strip()
    return re.sub(r'[^a-zA-Z0-9_-]', '', text)[:64]


def _analytics_report_generated_sort_value(record) -> int:
    if not isinstance(record, dict):
        return 0
    value = record.get('created_ts')
    try:
        return int(value or 0)
    except Exception:
        pass
    generated_at = str(record.get('generated_at') or '').strip()
    if generated_at:
        try:
            normalized = generated_at.replace('Z', '+00:00')
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=BEIJING_TZ)
            return int(parsed.timestamp())
        except Exception:
            return 0
    return 0


def _analytics_report_filename_part(value: str, fallback='report') -> str:
    text = str(value or '').strip()
    if not text:
        text = fallback
    text = re.sub(r'[\\/:*?"<>|\r\n\t]+', '-', text)
    text = re.sub(r'\s+', '-', text).strip(' .-_')
    return text[:80] or fallback


class SiteAnalyticsBusyError(RuntimeError):
    pass


class _AnalyticsFileLock:
    def __init__(self, path: Path, *, ttl_seconds=600, metadata=None):
        self.path = Path(path)
        self.ttl_seconds = max(30, int(ttl_seconds or 600))
        self.metadata = metadata if isinstance(metadata, dict) else {}
        self._fd = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            **self.metadata,
            'pid': os.getpid(),
            'created_ts': int(time.time()),
        }
        raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        for _attempt in range(2):
            try:
                self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self._fd, raw)
                return True
            except FileExistsError:
                if self._is_stale():
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    except Exception:
                        return False
                    continue
                return False
        return False

    def _is_stale(self) -> bool:
        try:
            return (time.time() - self.path.stat().st_mtime) > self.ttl_seconds
        except FileNotFoundError:
            return True
        except Exception:
            return False

    def read_metadata(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def release(self):
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            LOGGER.warning('Failed to release site analytics lock %s', self.path, exc_info=True)


def _analytics_read_json_file(path: Path, default=None):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return default
    return data


def _analytics_write_json_file(path: Path, data):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_name(f'.{target.name}.{uuid.uuid4().hex}.tmp')
    try:
        temp_path.write_text(
            json.dumps(data, ensure_ascii=False, separators=(',', ':')),
            encoding='utf-8',
        )
        os.replace(str(temp_path), str(target))
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass


def _current_admin_has_site_reports_access() -> bool:
    if not bool(session.get('admin_logged_in')):
        return False
    if bool(session.get('admin_is_super_admin', False)):
        return True
    raw_permissions = session.get('admin_permissions', [])
    if not isinstance(raw_permissions, (list, tuple, set)):
        return False
    return any(str(item or '').strip() == 'site-reports' for item in raw_permissions)


def _require_site_reports_admin_api():
    if _current_admin_has_site_reports_access():
        return None
    return jsonify({'success': False, 'message': '当前账号没有网站数据权限'}), 403


def _analytics_report_file_path(report_id: str) -> Path:
    safe_id = _analytics_report_safe_id(report_id)
    return SITE_ANALYTICS_AI_REPORTS_DIR / f'{safe_id}.json'


def _analytics_report_pdf_cache_path(report_id: str) -> Path:
    safe_id = _analytics_report_safe_id(report_id)
    return SITE_ANALYTICS_AI_REPORTS_PDF_DIR / f'{safe_id}-{SITE_ANALYTICS_AI_PDF_TEMPLATE_VERSION}.pdf'


def _analytics_report_pdf_cache_paths(report_id: str):
    safe_id = _analytics_report_safe_id(report_id)
    if not safe_id:
        return []
    paths = [_analytics_report_pdf_cache_path(safe_id)]
    legacy_path = SITE_ANALYTICS_AI_REPORTS_PDF_DIR / f'{safe_id}.pdf'
    if legacy_path not in paths:
        paths.append(legacy_path)
    try:
        for path in SITE_ANALYTICS_AI_REPORTS_PDF_DIR.glob(f'{safe_id}-v*.pdf'):
            if path not in paths:
                paths.append(path)
    except Exception:
        pass
    return paths


def _analytics_report_index_item(record):
    safe_record = record if isinstance(record, dict) else {}
    return {
        'id': _analytics_report_safe_id(safe_record.get('id')),
        'period': _analytics_clean_text(safe_record.get('period'), max_length=20),
        'period_label': _analytics_clean_text(safe_record.get('period_label'), max_length=20),
        'title': _analytics_ai_report_title(safe_record),
        'generated_at': _analytics_clean_text(safe_record.get('generated_at'), max_length=40),
        'created_ts': _analytics_report_generated_sort_value(safe_record) or int(time.time()),
        'model': _analytics_clean_text(safe_record.get('model'), max_length=80),
        'anchor_date': _analytics_clean_text(safe_record.get('anchor_date'), max_length=10),
        'current_range': safe_record.get('current_range') if isinstance(safe_record.get('current_range'), dict) else {},
        'previous_range': safe_record.get('previous_range') if isinstance(safe_record.get('previous_range'), dict) else {},
        'comparison': safe_record.get('comparison') if isinstance(safe_record.get('comparison'), dict) else {},
        'current_summary': safe_record.get('current_summary') if isinstance(safe_record.get('current_summary'), dict) else {},
    }


def _analytics_read_report_index():
    data = _analytics_read_json_file(SITE_ANALYTICS_AI_REPORTS_INDEX_FILE, default={})
    rows = data.get('reports') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    output = []
    seen = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        report_id = _analytics_report_safe_id(item.get('id'))
        if not report_id or report_id in seen:
            continue
        next_item = dict(item)
        next_item['id'] = report_id
        output.append(next_item)
        seen.add(report_id)
    output.sort(key=_analytics_report_generated_sort_value, reverse=True)
    return output


def _analytics_write_report_index(rows):
    safe_rows = []
    seen = set()
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        report_id = _analytics_report_safe_id(item.get('id'))
        if not report_id or report_id in seen:
            continue
        next_item = dict(item)
        next_item['id'] = report_id
        safe_rows.append(next_item)
        seen.add(report_id)
    safe_rows.sort(key=_analytics_report_generated_sort_value, reverse=True)
    _analytics_write_json_file(
        SITE_ANALYTICS_AI_REPORTS_INDEX_FILE,
        {'version': 1, 'reports': safe_rows, 'updated_ts': int(time.time())},
    )


def _analytics_ai_reports_per_period_limit():
    raw = os.environ.get('SITE_ANALYTICS_AI_REPORTS_PER_PERIOD_LIMIT')
    try:
        value = int(raw if raw is not None else SITE_ANALYTICS_AI_REPORTS_PER_PERIOD_LIMIT)
    except Exception:
        value = SITE_ANALYTICS_AI_REPORTS_PER_PERIOD_LIMIT
    return max(1, min(value, 500))


def _analytics_prune_report_store_locked(rows):
    limit = _analytics_ai_reports_per_period_limit()
    keep = []
    remove = []
    grouped = {}
    for item in rows if isinstance(rows, list) else []:
        period = _analytics_clean_text(item.get('period'), max_length=20).lower() or 'unknown'
        grouped.setdefault(period, []).append(item)
    for period_rows in grouped.values():
        period_rows.sort(key=_analytics_report_generated_sort_value, reverse=True)
        keep.extend(period_rows[:limit])
        remove.extend(period_rows[limit:])
    for item in remove:
        report_id = _analytics_report_safe_id(item.get('id'))
        if not report_id:
            continue
        for path in [_analytics_report_file_path(report_id), *_analytics_report_pdf_cache_paths(report_id)]:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                LOGGER.warning('Failed to prune site analytics report file %s', path, exc_info=True)
    keep.sort(key=_analytics_report_generated_sort_value, reverse=True)
    return keep


def _analytics_rebuild_report_index_locked():
    SITE_ANALYTICS_AI_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in SITE_ANALYTICS_AI_REPORTS_DIR.glob('*.json'):
        if path.name == SITE_ANALYTICS_AI_REPORTS_INDEX_FILE.name:
            continue
        record = _analytics_read_json_file(path, default=None)
        if isinstance(record, dict):
            report_id = _analytics_report_safe_id(record.get('id'))
            if report_id:
                record['id'] = report_id
                rows.append(_analytics_report_index_item(record))
    rows = _analytics_prune_report_store_locked(rows)
    _analytics_write_report_index(rows)
    return rows


def _analytics_import_legacy_report_jsonl_locked(rows):
    marker = SITE_ANALYTICS_AI_REPORTS_DIR / '.jsonl_imported'
    if marker.exists() or not SITE_ANALYTICS_AI_REPORTS_FILE.exists():
        return rows
    try:
        lines = SITE_ANALYTICS_AI_REPORTS_FILE.read_text(encoding='utf-8').splitlines()
    except Exception:
        lines = []
    existing = {_analytics_report_safe_id(item.get('id')) for item in rows if isinstance(item, dict)}
    imported = []
    seen_legacy = set()
    for line in reversed(lines):
        row = str(line or '').strip()
        if not row:
            continue
        try:
            record = json.loads(row)
        except Exception:
            continue
        if not isinstance(record, dict):
            continue
        report_id = _analytics_report_safe_id(record.get('id'))
        if not report_id or report_id in existing or report_id in seen_legacy:
            continue
        record['id'] = report_id
        record['created_ts'] = _analytics_report_generated_sort_value(record) or int(time.time())
        try:
            _analytics_write_json_file(_analytics_report_file_path(report_id), record)
            imported.append(_analytics_report_index_item(record))
            seen_legacy.add(report_id)
        except Exception:
            LOGGER.warning('Failed to import legacy site analytics AI report %s', report_id, exc_info=True)
    if imported:
        rows = imported + rows
        rows.sort(key=_analytics_report_generated_sort_value, reverse=True)
        rows = _analytics_prune_report_store_locked(rows)
        _analytics_write_report_index(rows)
    try:
        marker.write_text(str(int(time.time())), encoding='utf-8')
    except Exception:
        pass
    return rows


def _ensure_site_analytics_ai_report_store():
    SITE_ANALYTICS_AI_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    SITE_ANALYTICS_AI_REPORTS_PDF_DIR.mkdir(parents=True, exist_ok=True)
    with SITE_ANALYTICS_AI_REPORTS_LOCK:
        rows = _analytics_read_report_index()
        if not rows and any(SITE_ANALYTICS_AI_REPORTS_DIR.glob('*.json')):
            rows = _analytics_rebuild_report_index_locked()
        rows = _analytics_import_legacy_report_jsonl_locked(rows)
        if not SITE_ANALYTICS_AI_REPORTS_INDEX_FILE.exists():
            _analytics_write_report_index(rows)
        return rows


def _analytics_ai_report_title(record) -> str:
    if not isinstance(record, dict):
        return 'AI网站运营报告'
    existing = _analytics_clean_text(record.get('title'), max_length=120)
    if existing:
        return existing
    period_label = _analytics_clean_text(record.get('period_label'), max_length=20) or _analytics_report_period_label(record.get('period'))
    current_range = record.get('current_range') if isinstance(record.get('current_range'), dict) else {}
    start_date = _analytics_clean_text(current_range.get('start_date'), max_length=10)
    end_date = _analytics_clean_text(current_range.get('end_date'), max_length=10)
    if start_date and end_date:
        return f'{start_date} 至 {end_date} {period_label}'
    anchor = _analytics_clean_text(record.get('anchor_date'), max_length=10)
    return f'{anchor} {period_label}' if anchor else f'AI网站运营{period_label}'


def _analytics_public_ai_report_row(record):
    if not isinstance(record, dict):
        return {}
    current_range = record.get('current_range') if isinstance(record.get('current_range'), dict) else {}
    previous_range = record.get('previous_range') if isinstance(record.get('previous_range'), dict) else {}
    comparison = record.get('comparison') if isinstance(record.get('comparison'), dict) else {}
    current_summary = record.get('current_summary') if isinstance(record.get('current_summary'), dict) else {}
    return {
        'id': _analytics_report_safe_id(record.get('id')),
        'period': _analytics_clean_text(record.get('period'), max_length=20),
        'period_label': _analytics_clean_text(record.get('period_label'), max_length=20),
        'title': _analytics_ai_report_title(record),
        'generated_at': _analytics_clean_text(record.get('generated_at'), max_length=40),
        'model': _analytics_clean_text(record.get('model'), max_length=80),
        'anchor_date': _analytics_clean_text(record.get('anchor_date'), max_length=10),
        'current_range': current_range,
        'previous_range': previous_range,
        'comparison': comparison,
        'current_summary': current_summary,
        'download_url': f"/api/admin/site-reports/ai-reports/{_analytics_report_safe_id(record.get('id'))}/download",
    }


def _append_site_analytics_ai_report_record(record):
    if not isinstance(record, dict):
        return None
    safe_record = dict(record)
    safe_record['id'] = _analytics_report_safe_id(safe_record.get('id')) or uuid.uuid4().hex
    safe_record['created_ts'] = _analytics_report_generated_sort_value(safe_record) or int(time.time())
    SITE_ANALYTICS_AI_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    SITE_ANALYTICS_AI_REPORTS_PDF_DIR.mkdir(parents=True, exist_ok=True)
    with SITE_ANALYTICS_AI_REPORTS_LOCK:
        rows = _ensure_site_analytics_ai_report_store()
        _analytics_write_json_file(_analytics_report_file_path(safe_record['id']), safe_record)
        index_item = _analytics_report_index_item(safe_record)
        rows = [index_item] + [
            item for item in rows
            if _analytics_report_safe_id(item.get('id')) != safe_record['id']
        ]
        rows = _analytics_prune_report_store_locked(rows)
        _analytics_write_report_index(rows)
    return safe_record


def _iter_site_analytics_ai_report_records():
    return _ensure_site_analytics_ai_report_store()


def _get_site_analytics_ai_report_record(report_id: str):
    safe_id = _analytics_report_safe_id(report_id)
    if not safe_id:
        return None
    _ensure_site_analytics_ai_report_store()
    record = _analytics_read_json_file(_analytics_report_file_path(safe_id), default=None)
    if not isinstance(record, dict):
        return None
    record['id'] = safe_id
    return record


def _delete_site_analytics_ai_report_record(report_id: str) -> bool:
    safe_id = _analytics_report_safe_id(report_id)
    if not safe_id:
        return False
    with SITE_ANALYTICS_AI_REPORTS_LOCK:
        rows = _ensure_site_analytics_ai_report_store()
        exists = any(_analytics_report_safe_id(item.get('id')) == safe_id for item in rows)
        if not exists and not _analytics_report_file_path(safe_id).exists():
            return False
        next_rows = [
            item for item in rows
            if _analytics_report_safe_id(item.get('id')) != safe_id
        ]
        for path in [_analytics_report_file_path(safe_id), *_analytics_report_pdf_cache_paths(safe_id)]:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                LOGGER.warning('Failed to delete site analytics AI report file %s', path, exc_info=True)
        _analytics_write_report_index(next_rows)
    return True


def _build_site_analytics_ai_report_record(report_text: str, context, model: str, generated_at: str):
    safe_context = context if isinstance(context, dict) else {}
    period = _analytics_clean_text(safe_context.get('period'), max_length=20).lower() or 'month'
    period_label = _analytics_clean_text(safe_context.get('period_label'), max_length=20) or _analytics_report_period_label(period)
    current = safe_context.get('current') if isinstance(safe_context.get('current'), dict) else {}
    record = {
        'id': uuid.uuid4().hex,
        'period': period,
        'period_label': period_label,
        'title': '',
        'report': str(report_text or '').strip(),
        'generated_at': generated_at,
        'created_ts': int(time.time()),
        'model': _analytics_clean_text(model, max_length=80),
        'anchor_date': _analytics_clean_text(safe_context.get('anchor_date'), max_length=10),
        'current_range': safe_context.get('current_range') if isinstance(safe_context.get('current_range'), dict) else {},
        'previous_range': safe_context.get('previous_range') if isinstance(safe_context.get('previous_range'), dict) else {},
        'comparison': safe_context.get('comparison') if isinstance(safe_context.get('comparison'), dict) else {},
        'current_summary': current.get('summary') if isinstance(current.get('summary'), dict) else {},
        'current_detail': _analytics_report_detail_from_context(safe_context),
    }
    record['title'] = _analytics_ai_report_title(record)
    return record


def _analytics_inline_markdown_to_reportlab(text: str) -> str:
    escaped = html.escape(str(text or '').strip())
    escaped = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', escaped)
    escaped = re.sub(r'`([^`]+)`', r'<font face="Courier">\1</font>', escaped)
    return escaped


def _analytics_markdown_table_rows(lines):
    rows = []
    for line in lines:
        raw = str(line or '').strip()
        if not raw or '|' not in raw:
            continue
        cells = [cell.strip() for cell in raw.strip('|').split('|')]
        if cells and all(re.fullmatch(r':?-{3,}:?', cell or '') for cell in cells):
            continue
        rows.append(cells)
    return rows


def _analytics_format_pdf_metric_value(metric_key, value):
    if metric_key == 'avg_session_duration_sec':
        seconds = int(float(value or 0))
        minutes = seconds // 60
        remain = seconds % 60
        return f'{minutes}分{remain}秒' if minutes else f'{remain}秒'
    if metric_key in {'bounce_rate', 'conversion_rate'}:
        try:
            return f'{float(value or 0):.2f}%'
        except Exception:
            return '0.00%'
    try:
        num = float(value or 0)
    except Exception:
        return str(value or '0')
    if num.is_integer():
        return f'{int(num):,}'
    return f'{num:,.2f}'


def _analytics_format_pdf_change(item):
    if not isinstance(item, dict):
        return '持平'
    rate = item.get('change_rate')
    if rate is None:
        try:
            return '新增' if float(item.get('current') or 0) > 0 else '持平'
        except Exception:
            return '持平'
    try:
        num = float(rate or 0)
    except Exception:
        return '持平'
    if num == 0:
        return '持平'
    return f'{"+" if num > 0 else ""}{num:.2f}%'


def _analytics_report_detail_from_context(context):
    safe_context = context if isinstance(context, dict) else {}
    current = safe_context.get('current') if isinstance(safe_context.get('current'), dict) else {}
    return {
        'trend': _analytics_top_rows(current.get('trend'), 80),
        'source_breakdown': _analytics_top_rows(current.get('source_breakdown'), 8),
        'device_breakdown': _analytics_top_rows(current.get('device_breakdown'), 8),
        'os_breakdown': _analytics_top_rows(current.get('os_breakdown'), 8),
        'province_breakdown': _analytics_top_rows(current.get('province_breakdown'), 10),
        'continent_breakdown': _analytics_top_rows(current.get('continent_breakdown'), 8),
        'country_breakdown': _analytics_top_rows(current.get('country_breakdown'), 10),
        'top_pages': _analytics_top_rows(current.get('top_pages'), 12),
        'top_events': _analytics_top_rows(current.get('top_events'), 12),
    }


def _analytics_inline_markdown_to_html(text: str) -> str:
    escaped = html.escape(str(text or '').strip())
    escaped = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', escaped)
    escaped = re.sub(r'`([^`]+)`', r'<code>\1</code>', escaped)
    return escaped


def _analytics_markdown_to_report_html(text: str) -> str:
    raw = str(text or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not raw:
        return '<div class="empty-block">暂无报告内容</div>'

    lines = raw.split('\n')
    idx = 0
    output = []
    in_code = False
    code_lines = []

    def flush_code():
        if code_lines:
            output.append('<pre><code>' + html.escape('\n'.join(code_lines)) + '</code></pre>')
            code_lines.clear()

    while idx < len(lines):
        line = lines[idx].rstrip()
        stripped = line.strip()
        if stripped.startswith('```'):
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
                code_lines = []
            idx += 1
            continue

        if in_code:
            code_lines.append(line)
            idx += 1
            continue

        if not stripped:
            idx += 1
            continue
        if re.fullmatch(r'-{3,}|_{3,}|\*{3,}', stripped):
            output.append('<hr>')
            idx += 1
            continue

        if '|' in stripped and idx + 1 < len(lines) and re.search(r'\|\s*:?-{3,}:?\s*\|', lines[idx + 1]):
            table_lines = [stripped, lines[idx + 1].strip()]
            idx += 2
            while idx < len(lines) and '|' in lines[idx].strip():
                table_lines.append(lines[idx].strip())
                idx += 1
            rows = _analytics_markdown_table_rows(table_lines)
            if rows:
                header = rows[0]
                body = rows[1:]
                output.append('<div class="table-scroll"><table class="md-table"><thead><tr>')
                output.extend(f'<th>{_analytics_inline_markdown_to_html(cell)}</th>' for cell in header)
                output.append('</tr></thead><tbody>')
                for row in body:
                    output.append('<tr>')
                    for cell in row:
                        output.append(f'<td>{_analytics_inline_markdown_to_html(cell)}</td>')
                    output.append('</tr>')
                output.append('</tbody></table></div>')
            continue

        heading_match = re.match(r'^(#{1,4})\s+(.+)$', stripped)
        if heading_match:
            level = min(4, len(heading_match.group(1)) + 1)
            output.append(f'<h{level}>{_analytics_inline_markdown_to_html(heading_match.group(2))}</h{level}>')
            idx += 1
            continue

        if stripped.startswith('>'):
            quote_lines = []
            while idx < len(lines) and lines[idx].strip().startswith('>'):
                quote_lines.append(lines[idx].strip().lstrip('>').strip())
                idx += 1
            output.append('<blockquote>' + '<br>'.join(_analytics_inline_markdown_to_html(item) for item in quote_lines) + '</blockquote>')
            continue

        bullet_items = []
        while idx < len(lines):
            bullet_match = re.match(r'^\s*[-*]\s+(.+)$', lines[idx])
            if not bullet_match:
                break
            bullet_items.append(bullet_match.group(1))
            idx += 1
        if bullet_items:
            output.append('<ul>')
            output.extend(f'<li>{_analytics_inline_markdown_to_html(item)}</li>' for item in bullet_items)
            output.append('</ul>')
            continue

        ordered_items = []
        while idx < len(lines):
            ordered_match = re.match(r'^\s*\d+\.\s+(.+)$', lines[idx])
            if not ordered_match:
                break
            ordered_items.append(ordered_match.group(1))
            idx += 1
        if ordered_items:
            output.append('<ol>')
            output.extend(f'<li>{_analytics_inline_markdown_to_html(item)}</li>' for item in ordered_items)
            output.append('</ol>')
            continue

        paragraph_lines = [stripped]
        idx += 1
        while idx < len(lines):
            next_line = lines[idx].strip()
            if (
                not next_line
                or next_line.startswith('#')
                or next_line.startswith('>')
                or re.fullmatch(r'-{3,}|_{3,}|\*{3,}', next_line)
                or re.match(r'^\s*[-*]\s+', lines[idx])
                or re.match(r'^\s*\d+\.\s+', lines[idx])
                or (('|' in next_line) and idx + 1 < len(lines) and re.search(r'\|\s*:?-{3,}:?\s*\|', lines[idx + 1]))
            ):
                break
            paragraph_lines.append(next_line)
            idx += 1
        output.append('<p>' + '<br>'.join(_analytics_inline_markdown_to_html(item) for item in paragraph_lines) + '</p>')

    flush_code()
    return '\n'.join(output)


def _analytics_metric_tone(metric_key, item):
    if not isinstance(item, dict):
        return 'flat'
    try:
        change = float(item.get('change') or 0)
    except Exception:
        change = 0.0
    if change == 0:
        return 'flat'
    if metric_key == 'bounce_rate':
        return 'bad' if change > 0 else 'good'
    return 'good' if change > 0 else 'bad'


def _analytics_build_html_metric_cards(record):
    comparison = record.get('comparison') if isinstance(record.get('comparison'), dict) else {}
    metric_defs = [
        ('pageviews', '页面浏览量', 'PV'),
        ('unique_visitors', '独立访客', 'UV'),
        ('sessions', '会话数', 'Sessions'),
        ('avg_session_duration_sec', '平均会话时长', 'Duration'),
        ('bounce_rate', '跳出率', 'Bounce'),
        ('conversion_rate', '转化率', 'Conversion'),
    ]
    cards = []
    for key, fallback_label, en_label in metric_defs:
        item = comparison.get(key) if isinstance(comparison.get(key), dict) else {}
        label = _analytics_clean_text(item.get('label'), max_length=40) or fallback_label
        value = _analytics_format_pdf_metric_value(key, item.get('current'))
        previous = _analytics_format_pdf_metric_value(key, item.get('previous'))
        change = _analytics_format_pdf_change(item)
        tone = _analytics_metric_tone(key, item)
        cards.append(
            f'<div class="metric-card tone-{tone}">'
            f'<div class="metric-eyebrow">{html.escape(en_label)}</div>'
            f'<div class="metric-label">{html.escape(label)}</div>'
            f'<div class="metric-value">{html.escape(value)}</div>'
            f'<div class="metric-foot"><span>上期 {html.escape(previous)}</span><strong>环比 {html.escape(change)}</strong></div>'
            f'</div>'
        )
    return ''.join(cards)


def _analytics_report_detail(record):
    detail = record.get('current_detail') if isinstance(record.get('current_detail'), dict) else {}
    if any(isinstance(value, list) and value for value in detail.values()):
        return detail

    current_range = record.get('current_range') if isinstance(record.get('current_range'), dict) else {}
    start_date = _analytics_clean_text(current_range.get('start_date'), max_length=10)
    end_date = _analytics_clean_text(current_range.get('end_date'), max_length=10)
    if not start_date or not end_date:
        return detail

    granularity = _analytics_report_period_granularity(record.get('period'))
    try:
        report = build_site_analytics_report(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
        )
        return _analytics_compact_report_for_ai(report)
    except Exception:
        return detail
    return detail


def _analytics_compact_label(value, max_length=34):
    text = _analytics_clean_text(value, max_length=max_length)
    return text or '-'


def _analytics_bar_list_html(rows, *, label_key, value_key='sessions', ratio_key='ratio', limit=6, empty_text='暂无数据'):
    safe_rows = rows if isinstance(rows, list) else []
    safe_rows = [row for row in safe_rows if isinstance(row, dict)][:limit]
    if not safe_rows:
        return f'<div class="empty-block">{html.escape(empty_text)}</div>'
    max_value = max(float(row.get(value_key) or 0) for row in safe_rows) or 1
    output = []
    for row in safe_rows:
        label = _analytics_compact_label(row.get(label_key), max_length=42)
        value = float(row.get(value_key) or 0)
        ratio = row.get(ratio_key)
        try:
            ratio_text = f'{float(ratio or 0):.2f}%'
        except Exception:
            ratio_text = '-'
        width = max(4, min(100, value * 100.0 / max_value))
        output.append(
            '<div class="bar-row">'
            f'<div class="bar-row-head"><span>{html.escape(label)}</span><strong>{int(value):,} · {html.escape(ratio_text)}</strong></div>'
            f'<div class="bar-track"><i style="width:{width:.2f}%"></i></div>'
            '</div>'
        )
    return ''.join(output)


def _analytics_trend_svg_html(trend_rows):
    rows = [row for row in (trend_rows if isinstance(trend_rows, list) else []) if isinstance(row, dict)]
    if not rows:
        return '<div class="empty-block">暂无趋势数据</div>'
    values = [float(row.get('pageviews') or 0) for row in rows]
    max_value = max(values) or 1
    width = 760
    height = 190
    pad_x = 34
    pad_y = 28
    span = max(1, len(values) - 1)
    coords = []
    for idx, value in enumerate(values):
        x = pad_x + ((width - pad_x * 2) * idx / span)
        y = height - pad_y - ((height - pad_y * 2) * value / max_value)
        coords.append((x, y, value))
    point_text = ' '.join(f'{x:.2f},{y:.2f}' for x, y, _value in coords)
    area_points = f'{pad_x},{height - pad_y} {point_text} {width - pad_x},{height - pad_y}'
    circles = ''.join(
        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.2"><title>PV {value:g}</title></circle>'
        for x, y, value in coords
    )
    first_label = html.escape(str(rows[0].get('date') or ''))
    last_label = html.escape(str(rows[-1].get('date') or ''))
    grid_lines = ''.join(
        f'<line x1="{pad_x}" y1="{pad_y + i * ((height - pad_y * 2) / 4):.2f}" x2="{width - pad_x}" y2="{pad_y + i * ((height - pad_y * 2) / 4):.2f}" />'
        for i in range(5)
    )
    return (
        '<svg class="trend-svg" viewBox="0 0 760 190" role="img" aria-label="页面浏览量趋势">'
        f'<g class="trend-grid">{grid_lines}</g>'
        f'<polygon class="trend-area" points="{area_points}" />'
        f'<polyline class="trend-line" points="{point_text}" />'
        f'<g class="trend-points">{circles}</g>'
        f'<text x="{pad_x}" y="{height - 8}" class="trend-axis">{first_label}</text>'
        f'<text x="{width - pad_x}" y="{height - 8}" text-anchor="end" class="trend-axis">{last_label}</text>'
        f'<text x="{width - pad_x}" y="{pad_y - 8}" text-anchor="end" class="trend-max">峰值 PV {max_value:g}</text>'
        '</svg>'
    )


def _analytics_top_pages_table_html(rows):
    safe_rows = [row for row in (rows if isinstance(rows, list) else []) if isinstance(row, dict)][:8]
    if not safe_rows:
        return '<div class="empty-block">暂无热门页面数据</div>'
    output = ['<table class="data-table"><thead><tr><th>页面</th><th>PV</th><th>UV</th><th>会话</th></tr></thead><tbody>']
    for row in safe_rows:
        title = _analytics_clean_text(row.get('title'), max_length=52)
        path = _analytics_clean_text(row.get('path'), max_length=68)
        label = title or path or '-'
        output.append(
            '<tr>'
            f'<td><strong>{html.escape(label)}</strong><small>{html.escape(path)}</small></td>'
            f'<td>{int(float(row.get("pageviews") or 0)):,}</td>'
            f'<td>{int(float(row.get("unique_visitors") or 0)):,}</td>'
            f'<td>{int(float(row.get("sessions") or 0)):,}</td>'
            '</tr>'
        )
    output.append('</tbody></table>')
    return ''.join(output)


def _analytics_top_events_table_html(rows):
    safe_rows = [row for row in (rows if isinstance(rows, list) else []) if isinstance(row, dict)][:8]
    if not safe_rows:
        return '<div class="empty-block">暂无行为事件数据</div>'
    max_value = max(float(row.get('count') or 0) for row in safe_rows) or 1
    output = []
    for row in safe_rows:
        name = _analytics_clean_text(row.get('name'), max_length=50) or '-'
        count = float(row.get('count') or 0)
        width = max(4, min(100, count * 100.0 / max_value))
        output.append(
            '<div class="event-row">'
            f'<span>{html.escape(name)}</span><strong>{int(count):,}</strong>'
            f'<div class="bar-track"><i style="width:{width:.2f}%"></i></div>'
            '</div>'
        )
    return ''.join(output)


def _analytics_plain_int(value):
    try:
        return int(round(float(value or 0)))
    except Exception:
        return 0


def _analytics_plain_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _analytics_plain_number(value):
    return f'{_analytics_plain_int(value):,}'


def _analytics_plain_duration(seconds):
    total = _analytics_plain_int(seconds)
    if total <= 0:
        return '几乎没有停留'
    minutes = total // 60
    remain = total % 60
    if minutes >= 1:
        return f'{minutes}分{remain}秒'
    return f'{remain}秒'


def _analytics_plain_change_text(metric):
    if not isinstance(metric, dict):
        return ''
    current = _analytics_plain_float(metric.get('current'))
    previous = _analytics_plain_float(metric.get('previous'))
    change = current - previous
    if previous <= 0:
        if current > 0:
            return '上一周期几乎没有记录，这次开始有了数据。'
        return '这一项和上一周期一样，暂时没有明显变化。'
    if abs(change) < 0.0001:
        return '和上一周期基本持平。'
    rate = metric.get('change_rate')
    try:
        rate_text = f'{abs(float(rate)):.1f}%'
    except Exception:
        rate_text = ''
    direction = '多' if change > 0 else '少'
    suffix = f'，大约{rate_text}' if rate_text else ''
    return f'比上一周期{direction}了{_analytics_plain_number(abs(change))}{suffix}。'


def _analytics_plain_source_name(value):
    source = _analytics_clean_text(value, max_length=40).lower()
    mapping = {
        'direct': '直接访问或来源没识别出来',
        'referral': '外部网站跳转',
        'organic': '搜索引擎自然搜索',
        'organic_search': '搜索引擎自然搜索',
        'paid': '付费推广',
        'paid_search': '付费搜索',
        'social': '社交媒体',
        'email': '邮件',
    }
    return mapping.get(source, source or '暂时看不出来')


def _analytics_plain_event_name(value):
    name = _analytics_clean_text(value, max_length=50)
    mapping = {
        'scroll_depth': '页面滚动阅读',
        'engaged_15s': '停留超过 15 秒',
        'click_link': '链接点击',
        'click_button': '按钮点击',
        'submit_form': '表单提交',
        'click_phone': '电话点击',
        'click_email': '邮箱点击',
        'download_file': '资料下载',
    }
    return mapping.get(name, name or '暂时看不出来')


def _analytics_plain_top_page(rows):
    safe_rows = [row for row in (rows if isinstance(rows, list) else []) if isinstance(row, dict)]
    if not safe_rows:
        return {'label': '暂时看不出来', 'views': 0}
    row = safe_rows[0]
    title = _analytics_clean_text(row.get('title'), max_length=58)
    path = _analytics_clean_text(row.get('path'), max_length=70)
    return {
        'label': title or path or '暂时看不出来',
        'path': path,
        'views': _analytics_plain_int(row.get('pageviews')),
    }


def _analytics_plain_peak_day(trend_rows):
    safe_rows = [row for row in (trend_rows if isinstance(trend_rows, list) else []) if isinstance(row, dict)]
    if not safe_rows:
        return {'label': '暂时看不出来', 'views': 0, 'active_days': 0, 'total_days': 0}
    peak = max(safe_rows, key=lambda row: _analytics_plain_float(row.get('pageviews')))
    active_days = sum(1 for row in safe_rows if _analytics_plain_float(row.get('pageviews')) > 0)
    return {
        'label': _analytics_clean_text(
            peak.get('date') or peak.get('label') or peak.get('bucket_start'),
            max_length=30,
        ) or '暂时看不出来',
        'views': _analytics_plain_int(peak.get('pageviews')),
        'active_days': active_days,
        'total_days': len(safe_rows),
    }


def _analytics_build_plain_report_interpretation(record, detail=None):
    safe_record = record if isinstance(record, dict) else {}
    comparison = safe_record.get('comparison') if isinstance(safe_record.get('comparison'), dict) else {}
    detail = detail if isinstance(detail, dict) else _analytics_report_detail(safe_record)
    pageviews_metric = comparison.get('pageviews') if isinstance(comparison.get('pageviews'), dict) else {}
    visitors_metric = comparison.get('unique_visitors') if isinstance(comparison.get('unique_visitors'), dict) else {}
    sessions_metric = comparison.get('sessions') if isinstance(comparison.get('sessions'), dict) else {}
    duration_metric = comparison.get('avg_session_duration_sec') if isinstance(comparison.get('avg_session_duration_sec'), dict) else {}
    bounce_metric = comparison.get('bounce_rate') if isinstance(comparison.get('bounce_rate'), dict) else {}
    conversion_metric = comparison.get('conversion_events') if isinstance(comparison.get('conversion_events'), dict) else {}

    pageviews = _analytics_plain_int(pageviews_metric.get('current'))
    visitors = _analytics_plain_int(visitors_metric.get('current'))
    sessions = _analytics_plain_int(sessions_metric.get('current'))
    duration = _analytics_plain_int(duration_metric.get('current'))
    bounce_rate = _analytics_plain_float(bounce_metric.get('current'))
    conversions = _analytics_plain_int(conversion_metric.get('current'))
    top_page = _analytics_plain_top_page(detail.get('top_pages'))
    peak_day = _analytics_plain_peak_day(detail.get('trend'))

    sources = [row for row in (detail.get('source_breakdown') if isinstance(detail.get('source_breakdown'), list) else []) if isinstance(row, dict)]
    top_source = sources[0] if sources else {}
    source_name = _analytics_plain_source_name(top_source.get('source'))
    source_sessions = _analytics_plain_int(top_source.get('sessions'))

    events = [row for row in (detail.get('top_events') if isinstance(detail.get('top_events'), list) else []) if isinstance(row, dict)]
    top_event = events[0] if events else {}
    event_name = _analytics_plain_event_name(top_event.get('name'))
    event_count = _analytics_plain_int(top_event.get('count'))
    duration_text = _analytics_plain_duration(duration)

    if visitors <= 0 or pageviews <= 0:
        headline = '当前周期网站有效访问偏少，建议优先核查推广动作是否持续，以及统计代码是否正常工作。'
    elif conversions <= 0:
        headline = '当前周期网站已形成一定访问规模，但尚未记录明确咨询线索；下一步应加强从内容浏览到产品、方案与联系入口的转化引导。'
    else:
        headline = f'当前周期网站访问与转化均有表现，共记录 {_analytics_plain_number(conversions)} 次潜在咨询或转化动作，建议继续放大有效内容与高意向入口。'

    cards = [
        {
            'title': '访客规模',
            'value': f'{_analytics_plain_number(visitors)} 人',
            'note': (
                f'本周期共记录 {_analytics_plain_number(pageviews)} 次页面浏览，形成 {_analytics_plain_number(sessions)} 次访问会话。'
                f'{_analytics_plain_change_text(visitors_metric)}'
            ),
        },
        {
            'title': '访问深度',
            'value': duration_text,
            'note': f'平均每次访问停留约 {duration_text}；跳出率为 {bounce_rate:.1f}%，需要继续强化页面内的下一步行动入口。',
        },
        {
            'title': '线索转化',
            'value': f'{_analytics_plain_number(conversions)} 次',
            'note': '该指标统计表单、电话、邮箱、资料下载等能够代表客户意向的关键动作，用于评估访问流量是否转化为可跟进线索。',
        },
        {
            'title': '重点内容',
            'value': top_page['label'],
            'note': f'该页面被打开 {_analytics_plain_number(top_page["views"])} 次，适合进一步补充产品方案、咨询按钮和联系方式。',
        },
    ]

    points = [
        f'本周期共有 {_analytics_plain_number(visitors)} 位独立访客访问网站，合计产生 {_analytics_plain_number(pageviews)} 次页面浏览。',
        f'访问峰值出现在 {peak_day["label"]}，当天页面浏览量为 {_analytics_plain_number(peak_day["views"])} 次；整个周期内 {peak_day["active_days"]}/{peak_day["total_days"]} 天有访问记录。',
        f'主要来源为“{source_name}”，对应 {_analytics_plain_number(source_sessions)} 次访问；如来源长期无法识别，建议为推广链接补充追踪参数。',
        f'最高频行为事件为“{event_name}”，共发生 {_analytics_plain_number(event_count)} 次；如咨询类点击偏少，需要增强页面行动引导。',
    ]

    actions = [
        '把访问最多的页面当成重点入口，在页面中加醒目的“获取方案 / 联系技术工程师 / 下载资料”。',
        '检查电话、表单、邮箱、微信复制、资料下载等关键动作是否已纳入统计，避免因转化记录缺失造成经营判断偏差。',
        '如果热门内容多是新闻，就要在新闻里嵌入产品和解决方案入口，把读文章的人带到能产生商机的页面。',
    ]

    return {
        'headline': headline,
        'cards': cards,
        'points': points,
        'actions': actions,
    }


def _analytics_plain_interpretation_html(plain):
    safe_plain = plain if isinstance(plain, dict) else {}
    cards = safe_plain.get('cards') if isinstance(safe_plain.get('cards'), list) else []
    points = safe_plain.get('points') if isinstance(safe_plain.get('points'), list) else []
    actions = safe_plain.get('actions') if isinstance(safe_plain.get('actions'), list) else []
    cards_html = ''.join(
        '<div class="plain-card">'
        f'<span>{html.escape(str(card.get("title") or ""))}</span>'
        f'<strong>{html.escape(str(card.get("value") or "-"))}</strong>'
        f'<p>{html.escape(str(card.get("note") or ""))}</p>'
        '</div>'
        for card in cards
        if isinstance(card, dict)
    )
    points_html = ''.join(f'<li>{html.escape(str(item or ""))}</li>' for item in points)
    actions_html = ''.join(f'<li>{html.escape(str(item or ""))}</li>' for item in actions)
    return (
        '<div class="plain-hero">'
        '<span>总体判断</span>'
        f'<p>{html.escape(str(safe_plain.get("headline") or ""))}</p>'
        '</div>'
        f'<div class="plain-card-grid">{cards_html}</div>'
        '<div class="plain-two-col">'
        f'<div class="plain-block"><h3>核心观察</h3><ol>{points_html}</ol></div>'
        f'<div class="plain-block action"><h3>当前需重点关注</h3><ol>{actions_html}</ol></div>'
        '</div>'
    )


def _analytics_split_markdown_report_pages(text: str, max_chars=1650):
    raw = str(text or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not raw:
        return ['']
    chunks = []
    current = []
    current_len = 0
    in_code = False

    def flush():
        nonlocal current, current_len
        chunk = '\n'.join(current).strip()
        if chunk:
            chunks.append(chunk)
        current = []
        current_len = 0

    for line in raw.split('\n'):
        stripped = line.strip()
        is_code_fence = stripped.startswith('```')
        starts_section = bool(re.match(r'^#{1,3}\s+', stripped))
        line_len = len(line) + 1
        should_split = (
            current
            and not in_code
            and (
                current_len + line_len > max_chars
                or (starts_section and current_len > max_chars * 0.55)
            )
        )
        if should_split:
            flush()
        current.append(line)
        current_len += line_len
        if is_code_fence:
            in_code = not in_code

    flush()
    return chunks or ['']


def _analytics_ai_report_pages_html(report_text):
    chunks = _analytics_split_markdown_report_pages(report_text)
    pages = []
    for idx, chunk in enumerate(chunks):
        section_label = '策略洞察与行动建议' if idx == 0 else f'策略洞察与行动建议 · 续 {idx + 1}'
        pages.append(
            '<section class="report-page content-page">'
            f'<div class="section-head"><h2>AI 运营分析</h2><span>{html.escape(section_label)}</span></div>'
            f'<article class="report-body">{_analytics_markdown_to_report_html(chunk)}</article>'
            '<div class="footer"><span>MetaChip Website Analytics</span><span>AI Generated Analysis</span></div>'
            '</section>'
        )
    return '\n'.join(pages)


def _build_site_analytics_ai_report_html(record):
    safe_record = record if isinstance(record, dict) else {}
    detail = _analytics_report_detail(safe_record)
    title = _analytics_ai_report_title(safe_record)
    period_label = _analytics_clean_text(safe_record.get('period_label'), max_length=20) or _analytics_report_period_label(safe_record.get('period'))
    current_range = safe_record.get('current_range') if isinstance(safe_record.get('current_range'), dict) else {}
    previous_range = safe_record.get('previous_range') if isinstance(safe_record.get('previous_range'), dict) else {}
    generated_at = _analytics_clean_text(safe_record.get('generated_at'), max_length=40)
    model = _analytics_clean_text(safe_record.get('model'), max_length=80)
    plain_html = _analytics_plain_interpretation_html(_analytics_build_plain_report_interpretation(safe_record, detail))
    ai_pages_html = _analytics_ai_report_pages_html(safe_record.get('report'))
    trend_html = _analytics_trend_svg_html(detail.get('trend'))
    source_html = _analytics_bar_list_html(detail.get('source_breakdown'), label_key='source', empty_text='暂无渠道来源数据')
    device_html = _analytics_bar_list_html(detail.get('device_breakdown'), label_key='device', empty_text='暂无设备数据')
    pages_html = _analytics_top_pages_table_html(detail.get('top_pages'))
    events_html = _analytics_top_events_table_html(detail.get('top_events'))
    province_html = _analytics_bar_list_html(detail.get('province_breakdown'), label_key='province', empty_text='暂无省份数据')
    country_html = _analytics_bar_list_html(detail.get('country_breakdown'), label_key='country', empty_text='暂无国家数据')
    css = """
<style>
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #e9eef4; color: #172033; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "Noto Sans CJK SC", "PingFang SC", Arial, sans-serif;
  font-size: 13px;
  line-height: 1.65;
}
.report-page {
  width: 210mm;
  height: 297mm;
  margin: 0 auto;
  padding: 18mm 17mm 16mm;
  background: #fff;
  position: relative;
  page-break-after: always;
  overflow: hidden;
}
.report-page:last-child { page-break-after: auto; }
.cover { color: #0f1f37; display: flex; flex-direction: column; }
.cover::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 8mm;
  background: linear-gradient(90deg, #123d71, #0f766e 58%, #f59e0b);
}
.brand-row { display: flex; justify-content: space-between; align-items: flex-start; margin-top: 10mm; }
.brand-mark { display: flex; gap: 10px; align-items: center; color: #123d71; font-weight: 800; letter-spacing: .02em; }
.brand-icon { width: 34px; height: 34px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; background: #123d71; color: #fff; font-size: 18px; }
.report-kind { padding: 6px 12px; border-radius: 999px; background: #ecfdf5; color: #047857; font-weight: 800; }
.cover-title { margin: 24mm 0 10mm; max-width: 142mm; }
.cover-title h1 { margin: 0; font-size: 34px; line-height: 1.18; letter-spacing: 0; color: #10233d; }
.cover-title p { margin: 12px 0 0; color: #526173; font-size: 15px; }
.cover-meta { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 7mm 0 12mm; }
.meta-card { border: 1px solid #dbe6f5; border-radius: 8px; padding: 13px 14px; background: #f8fbff; }
.meta-card span { display: block; color: #64748b; font-size: 12px; margin-bottom: 4px; }
.meta-card strong { color: #10233d; font-size: 14px; }
.metric-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 8mm; }
.metric-card { border: 1px solid #dbe6f5; border-radius: 8px; padding: 13px; background: #fff; box-shadow: 0 8px 22px rgba(15, 23, 42, .06); }
.metric-eyebrow { color: #8aa0b8; font-size: 10px; text-transform: uppercase; font-weight: 800; }
.metric-label { color: #526173; font-size: 12px; margin-top: 2px; }
.metric-value { color: #0f1f37; font-size: 24px; font-weight: 850; line-height: 1.25; margin-top: 5px; }
.metric-foot { display: flex; justify-content: space-between; gap: 8px; margin-top: 8px; font-size: 11px; color: #64748b; }
.metric-foot strong { color: #2563eb; }
.tone-good { border-top: 4px solid #10b981; }
.tone-bad { border-top: 4px solid #ef4444; }
.tone-flat { border-top: 4px solid #94a3b8; }
.cover-note { margin-top: auto; padding-top: 12mm; color: #64748b; font-size: 12px; }
.section-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; margin-bottom: 12px; border-bottom: 1px solid #dbe6f5; padding-bottom: 10px; }
.section-head h2 { margin: 0; color: #10233d; font-size: 22px; }
.section-head span { color: #64748b; font-size: 12px; }
.panel-grid { display: grid; grid-template-columns: 1.18fr .82fr; gap: 12px; margin-bottom: 12px; }
.panel { border: 1px solid #dbe6f5; border-radius: 8px; padding: 14px; background: #fff; break-inside: avoid; }
.panel h3 { margin: 0 0 10px; color: #123d71; font-size: 15px; }
.trend-svg { width: 100%; height: auto; display: block; background: #f8fbff; border-radius: 8px; }
.trend-grid line { stroke: #dce7f3; stroke-width: 1; }
.trend-area { fill: rgba(37, 99, 235, .12); }
.trend-line { fill: none; stroke: #2563eb; stroke-width: 3.2; stroke-linecap: round; stroke-linejoin: round; }
.trend-points circle { fill: #0f766e; stroke: #fff; stroke-width: 2; }
.trend-axis, .trend-max { fill: #64748b; font-size: 11px; }
.bar-row, .event-row { margin-bottom: 10px; break-inside: avoid; }
.bar-row-head { display: flex; justify-content: space-between; gap: 10px; color: #334155; font-size: 12px; }
.bar-row-head strong, .event-row strong { color: #10233d; }
.bar-track { height: 7px; background: #edf2f7; border-radius: 999px; overflow: hidden; margin-top: 5px; }
.bar-track i { display: block; height: 100%; background: linear-gradient(90deg, #2563eb, #0f766e); border-radius: inherit; }
.event-row { display: grid; grid-template-columns: 1fr auto; gap: 8px; color: #334155; }
.event-row .bar-track { grid-column: 1 / -1; }
.data-table, .md-table { width: 100%; border-collapse: collapse; font-size: 11.5px; }
.data-table th, .data-table td, .md-table th, .md-table td { border-bottom: 1px solid #e2e8f0; padding: 8px 7px; vertical-align: top; text-align: left; }
.data-table th, .md-table th { background: #f1f7ff; color: #123d71; font-weight: 800; }
.data-table td:not(:first-child), .md-table td:not(:first-child) { white-space: nowrap; }
.data-table small { display: block; color: #94a3b8; font-size: 10px; margin-top: 2px; word-break: break-all; }
.plain-page { padding-top: 15mm; }
.plain-hero { margin: 4mm 0 8mm; padding: 18px 20px; border-radius: 8px; background: #10233d; color: #fff; }
.plain-hero span { display: block; color: #a7f3d0; font-size: 12px; font-weight: 800; margin-bottom: 7px; }
.plain-hero p { margin: 0; font-size: 20px; line-height: 1.65; font-weight: 800; }
.plain-card-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 14px; }
.plain-card { border: 1px solid #dbe6f5; border-radius: 8px; padding: 14px; background: #f8fbff; break-inside: avoid; }
.plain-card span { color: #64748b; font-size: 12px; font-weight: 800; }
.plain-card strong { display: block; margin: 4px 0 7px; color: #123d71; font-size: 21px; line-height: 1.25; }
.plain-card p { margin: 0; color: #334155; font-size: 12.5px; }
.plain-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.plain-block { border: 1px solid #dbe6f5; border-radius: 8px; padding: 15px; background: #fff; break-inside: avoid; }
.plain-block.action { background: #fffbeb; border-color: #fde68a; }
.plain-block h3 { margin: 0 0 9px; color: #123d71; font-size: 15px; }
.plain-block ol { margin: 0 0 0 19px; padding: 0; }
.plain-block li { margin: 7px 0; color: #334155; font-size: 12.5px; line-height: 1.65; }
.content-page { padding-top: 15mm; }
.report-body { color: #263548; }
.report-body h2 { margin: 16px 0 8px; color: #123d71; font-size: 19px; border-left: 4px solid #0f766e; padding-left: 9px; break-after: avoid; }
.report-body h3 { margin: 13px 0 7px; color: #17436f; font-size: 15px; break-after: avoid; }
.report-body h4 { margin: 10px 0 6px; color: #334155; font-size: 13px; break-after: avoid; }
.report-body p { margin: 0 0 8px; }
.report-body ul, .report-body ol { margin: 0 0 9px 20px; padding: 0; }
.report-body li { margin: 3px 0; }
.report-body blockquote { margin: 10px 0; padding: 9px 12px; border-left: 4px solid #f59e0b; background: #fffbeb; color: #5b4730; }
.report-body hr { border: 0; border-top: 1px solid #dbe6f5; margin: 13px 0; }
.table-scroll { margin: 10px 0 12px; break-inside: avoid; }
.empty-block { min-height: 60px; border: 1px dashed #cbd5e1; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: #94a3b8; background: #f8fafc; }
.footer { position: absolute; left: 17mm; right: 17mm; bottom: 8mm; display: flex; justify-content: space-between; color: #94a3b8; font-size: 10px; border-top: 1px solid #e5e7eb; padding-top: 5px; }
code { font-family: Consolas, Monaco, monospace; background: #f1f5f9; padding: 1px 4px; border-radius: 4px; }
pre { white-space: pre-wrap; background: #0f172a; color: #e2e8f0; border-radius: 8px; padding: 12px; font-size: 11px; }
</style>
"""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
{css}
</head>
<body>
<section class="report-page cover">
  <div class="brand-row">
    <div class="brand-mark"><span class="brand-icon">M</span><span>元芯传感 MetaChip</span></div>
    <div class="report-kind">{html.escape(period_label)}</div>
  </div>
  <div class="cover-title">
    <h1>{html.escape(title)}</h1>
    <p>面向经营与营销决策的网站运营分析报告</p>
  </div>
  <div class="cover-meta">
    <div class="meta-card"><span>统计周期</span><strong>{html.escape(str(current_range.get('label') or '-'))}</strong></div>
    <div class="meta-card"><span>环比周期</span><strong>{html.escape(str(previous_range.get('label') or '-'))}</strong></div>
    <div class="meta-card"><span>生成时间</span><strong>{html.escape(generated_at or '-')}</strong></div>
    <div class="meta-card"><span>分析模型</span><strong>{html.escape(model or '-')}</strong></div>
  </div>
  <div class="metric-grid">{_analytics_build_html_metric_cards(safe_record)}</div>
  <div class="cover-note">本 PDF 由后台聚合数据与 AI 分析内容生成，不包含原始 IP、访客 ID 或会话 ID。</div>
  <div class="footer"><span>MetaChip Website Analytics</span><span>Confidential · Internal Report</span></div>
</section>
<section class="report-page">
  <div class="section-head"><h2>简要总结</h2><span>面向经营决策的关键解读</span></div>
  {plain_html}
  <div class="footer"><span>MetaChip Website Analytics</span><span>Executive Summary</span></div>
</section>
<section class="report-page">
  <div class="section-head"><h2>数据概览</h2><span>趋势、渠道与设备</span></div>
  <div class="panel"><h3>PV 趋势</h3>{trend_html}</div>
  <div class="panel-grid">
    <div class="panel"><h3>流量来源</h3>{source_html}</div>
    <div class="panel"><h3>设备类型</h3>{device_html}</div>
  </div>
  <div class="footer"><span>MetaChip Website Analytics</span><span>Data Overview</span></div>
</section>
<section class="report-page">
  <div class="section-head"><h2>内容与地域分布</h2><span>热门页面、行为事件与地域表现</span></div>
  <div class="panel-grid">
    <div class="panel"><h3>热门页面</h3>{pages_html}</div>
    <div class="panel"><h3>行为事件</h3>{events_html}</div>
  </div>
  <div class="panel-grid">
    <div class="panel"><h3>中国省份分布</h3>{province_html}</div>
    <div class="panel"><h3>国家/地区分布</h3>{country_html}</div>
  </div>
  <div class="footer"><span>MetaChip Website Analytics</span><span>Data Overview</span></div>
</section>
{ai_pages_html}
</body>
</html>"""


def _find_site_report_chromium_executable():
    env_path = str(os.environ.get('SITE_REPORT_CHROMIUM_PATH') or '').strip()
    candidates = [env_path] if env_path else []
    candidates.extend([
        shutil.which('chromium'),
        shutil.which('chromium-browser'),
        shutil.which('google-chrome'),
        shutil.which('google-chrome-stable'),
        shutil.which('msedge'),
        shutil.which('chrome'),
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    ])
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return ''


def _generate_site_analytics_ai_report_pdf_chromium(record):
    html_text = _build_site_analytics_ai_report_html(record)
    executable_path = _find_site_report_chromium_executable()
    if not executable_path:
        raise RuntimeError('未找到 Chrome/Chromium，无法使用精美 HTML 模板导出 PDF。')

    with tempfile.TemporaryDirectory(prefix='site-report-pdf-') as temp_dir:
        temp_root = Path(temp_dir)
        html_path = temp_root / 'report.html'
        pdf_path = temp_root / 'report.pdf'
        profile_path = temp_root / 'chrome-profile'
        html_path.write_text(html_text, encoding='utf-8')

        command = [
            executable_path,
            '--headless',
            '--disable-gpu',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-background-networking',
            '--disable-extensions',
            '--no-first-run',
            '--allow-file-access-from-files',
            '--run-all-compositor-stages-before-draw',
            '--virtual-time-budget=5000',
            f'--user-data-dir={profile_path}',
            f'--print-to-pdf={pdf_path}',
            '--print-to-pdf-no-header',
            html_path.resolve().as_uri(),
        ]
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=90,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('精美PDF生成超时，请稍后重试。') from exc
        except Exception as exc:
            raise RuntimeError(f'精美PDF生成失败: {str(exc)}') from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or '').strip()
            raise RuntimeError(f'精美PDF生成失败: {detail[:500] or "Chromium 返回异常"}')
        if not pdf_path.exists() or pdf_path.stat().st_size <= 0:
            detail = (result.stderr or result.stdout or '').strip()
            raise RuntimeError(f'精美PDF生成失败: {detail[:500] or "未生成 PDF 文件"}')

        pdf_bytes = pdf_path.read_bytes()

    buffer = io.BytesIO(pdf_bytes)
    buffer.seek(0)
    return buffer


def _generate_site_analytics_ai_report_pdf(record):
    safe_record = record if isinstance(record, dict) else {}
    report_id = _analytics_report_safe_id(safe_record.get('id'))
    cache_path = _analytics_report_pdf_cache_path(report_id) if report_id else None
    if cache_path and cache_path.exists() and cache_path.stat().st_size > 0:
        buffer = io.BytesIO(cache_path.read_bytes())
        buffer.seek(0)
        return buffer

    lock = _AnalyticsFileLock(
        SITE_ANALYTICS_AI_PDF_LOCK_FILE,
        ttl_seconds=SITE_ANALYTICS_AI_PDF_LOCK_TTL_SECONDS,
        metadata={'type': 'site-report-pdf', 'report_id': report_id},
    )
    if not lock.acquire():
        raise SiteAnalyticsBusyError('PDF 正在生成中，请稍后再试。')
    try:
        if cache_path and cache_path.exists() and cache_path.stat().st_size > 0:
            buffer = io.BytesIO(cache_path.read_bytes())
            buffer.seek(0)
            return buffer
        try:
            pdf_buffer = _generate_site_analytics_ai_report_pdf_chromium(record)
        except Exception as exc:
            LOGGER.warning('Chromium site analytics PDF generation failed; falling back to ReportLab.', exc_info=True)
            pdf_buffer = _generate_site_analytics_ai_report_pdf_reportlab(record)
        pdf_bytes = pdf_buffer.getvalue()
        if cache_path and pdf_bytes:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = cache_path.with_name(f'.{cache_path.name}.{uuid.uuid4().hex}.tmp')
            try:
                temp_path.write_bytes(pdf_bytes)
                os.replace(str(temp_path), str(cache_path))
            finally:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass
                except Exception:
                    pass
        output = io.BytesIO(pdf_bytes)
        output.seek(0)
        return output
    finally:
        lock.release()


def _generate_site_analytics_ai_report_pdf_reportlab(record):
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import (
            KeepTogether,
            ListFlowable,
            ListItem,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except Exception as exc:
        raise RuntimeError('PDF导出依赖 reportlab 未安装，请先执行 pip install -r requirements.txt 后重试。') from exc

    try:
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    except Exception as exc:
        LOGGER.exception('ReportLab Chinese font registration failed for site analytics PDF.')
        raise RuntimeError('PDF 中文字体注册失败，无法可靠导出中文报告。请检查 reportlab 与中文字体环境。') from exc

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title=_analytics_ai_report_title(record),
        author='元芯传感网站后台',
    )

    base_font = 'STSong-Light'
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='ReportTitle',
        parent=styles['Title'],
        fontName=base_font,
        fontSize=22,
        leading=30,
        textColor=colors.HexColor('#10233d'),
        alignment=TA_CENTER,
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name='ReportMeta',
        parent=styles['Normal'],
        fontName=base_font,
        fontSize=9,
        leading=14,
        textColor=colors.HexColor('#64748b'),
        alignment=TA_CENTER,
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name='ReportH2',
        parent=styles['Heading2'],
        fontName=base_font,
        fontSize=15,
        leading=22,
        textColor=colors.HexColor('#123d71'),
        spaceBefore=14,
        spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name='ReportH3',
        parent=styles['Heading3'],
        fontName=base_font,
        fontSize=12,
        leading=18,
        textColor=colors.HexColor('#1f4f82'),
        spaceBefore=10,
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name='ReportBody',
        parent=styles['BodyText'],
        fontName=base_font,
        fontSize=10.5,
        leading=17,
        textColor=colors.HexColor('#1f2937'),
        alignment=TA_LEFT,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name='ReportSmall',
        parent=styles['BodyText'],
        fontName=base_font,
        fontSize=8.5,
        leading=13,
        textColor=colors.HexColor('#64748b'),
    ))
    styles.add(ParagraphStyle(
        name='ReportPlainHero',
        parent=styles['BodyText'],
        fontName=base_font,
        fontSize=14,
        leading=22,
        textColor=colors.HexColor('#10233d'),
        backColor=colors.HexColor('#eef6ff'),
        borderColor=colors.HexColor('#dbe6f5'),
        borderWidth=0.7,
        borderPadding=9,
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name='ReportPlainLabel',
        parent=styles['BodyText'],
        fontName=base_font,
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=2,
    ))

    story = []
    title = _analytics_ai_report_title(record)
    current_range = record.get('current_range') if isinstance(record.get('current_range'), dict) else {}
    previous_range = record.get('previous_range') if isinstance(record.get('previous_range'), dict) else {}
    generated_at = _analytics_clean_text(record.get('generated_at'), max_length=40)
    model = _analytics_clean_text(record.get('model'), max_length=80)
    meta_parts = [
        f"报告周期：{_analytics_clean_text(record.get('period_label'), max_length=20) or _analytics_report_period_label(record.get('period'))}",
        f"当前周期：{current_range.get('label') or '-'}",
        f"环比周期：{previous_range.get('label') or '-'}",
        f"生成时间：{generated_at or '-'}",
    ]
    if model:
        meta_parts.append(f"模型：{model}")
    story.append(Paragraph(_analytics_inline_markdown_to_reportlab(title), styles['ReportTitle']))
    story.append(Paragraph('　|　'.join(html.escape(str(part)) for part in meta_parts), styles['ReportMeta']))

    comparison = record.get('comparison') if isinstance(record.get('comparison'), dict) else {}
    metric_keys = ['pageviews', 'unique_visitors', 'sessions', 'bounce_rate', 'conversion_events', 'conversion_rate']
    kpi_rows = []
    row = []
    for key in metric_keys:
        item = comparison.get(key) if isinstance(comparison.get(key), dict) else {}
        label = _analytics_clean_text(item.get('label'), max_length=40) or key
        current_value = _analytics_format_pdf_metric_value(key, item.get('current'))
        change_value = _analytics_format_pdf_change(item)
        cell = Paragraph(
            f'<font color="#64748b">{html.escape(label)}</font><br/>'
            f'<font size="15" color="#10233d">{html.escape(current_value)}</font><br/>'
            f'<font color="#2563eb">环比 {html.escape(change_value)}</font>',
            styles['ReportBody'],
        )
        row.append(cell)
        if len(row) == 3:
            kpi_rows.append(row)
            row = []
    if row:
        while len(row) < 3:
            row.append(Paragraph('', styles['ReportBody']))
        kpi_rows.append(row)
    if kpi_rows:
        table = Table(kpi_rows, colWidths=[54 * mm, 54 * mm, 54 * mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fbff')),
            ('BOX', (0, 0), (-1, -1), 0.7, colors.HexColor('#dbe6f5')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dbe6f5')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        story.append(KeepTogether([table, Spacer(1, 8)]))

    plain = _analytics_build_plain_report_interpretation(record)
    story.append(PageBreak())
    story.append(Paragraph('简要总结', styles['ReportTitle']))
    story.append(Paragraph('面向经营决策的关键解读', styles['ReportMeta']))
    story.append(Paragraph(_analytics_inline_markdown_to_reportlab(plain.get('headline')), styles['ReportPlainHero']))

    plain_cards = []
    row = []
    for card in plain.get('cards') if isinstance(plain.get('cards'), list) else []:
        if not isinstance(card, dict):
            continue
        cell = Paragraph(
            f'<font color="#64748b">{html.escape(str(card.get("title") or ""))}</font><br/>'
            f'<font size="14" color="#123d71">{html.escape(str(card.get("value") or "-"))}</font><br/>'
            f'{_analytics_inline_markdown_to_reportlab(card.get("note"))}',
            styles['ReportBody'],
        )
        row.append(cell)
        if len(row) == 2:
            plain_cards.append(row)
            row = []
    if row:
        row.append(Paragraph('', styles['ReportBody']))
        plain_cards.append(row)
    if plain_cards:
        plain_table = Table(plain_cards, colWidths=[80 * mm, 80 * mm])
        plain_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fbff')),
            ('BOX', (0, 0), (-1, -1), 0.7, colors.HexColor('#dbe6f5')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dbe6f5')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        story.append(KeepTogether([plain_table, Spacer(1, 8)]))

    story.append(Paragraph('核心观察', styles['ReportH2']))
    plain_points = [
        ListItem(Paragraph(_analytics_inline_markdown_to_reportlab(item), styles['ReportBody']), leftIndent=10)
        for item in (plain.get('points') if isinstance(plain.get('points'), list) else [])
    ]
    if plain_points:
        story.append(ListFlowable(plain_points, bulletType='1', leftIndent=14, bulletFontName=base_font))
    story.append(Paragraph('当前需重点关注', styles['ReportH2']))
    plain_actions = [
        ListItem(Paragraph(_analytics_inline_markdown_to_reportlab(item), styles['ReportBody']), leftIndent=10)
        for item in (plain.get('actions') if isinstance(plain.get('actions'), list) else [])
    ]
    if plain_actions:
        story.append(ListFlowable(plain_actions, bulletType='1', leftIndent=14, bulletFontName=base_font))

    story.append(PageBreak())
    story.append(Paragraph('AI 运营分析', styles['ReportTitle']))
    story.append(Paragraph('策略洞察与行动建议', styles['ReportMeta']))

    report_text = str(record.get('report') or '').strip()
    lines = report_text.splitlines()
    idx = 0
    in_code = False
    while idx < len(lines):
        line = lines[idx].rstrip()
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code = not in_code
            idx += 1
            continue
        if not stripped:
            story.append(Spacer(1, 4))
            idx += 1
            continue

        if in_code:
            story.append(Paragraph(_analytics_inline_markdown_to_reportlab(stripped), styles['ReportSmall']))
            idx += 1
            continue

        if '|' in stripped and idx + 1 < len(lines) and re.search(r'\|\s*:?-{3,}:?\s*\|', lines[idx + 1]):
            table_lines = [stripped, lines[idx + 1].strip()]
            idx += 2
            while idx < len(lines) and '|' in lines[idx].strip():
                table_lines.append(lines[idx].strip())
                idx += 1
            rows = _analytics_markdown_table_rows(table_lines)
            if rows:
                max_cols = min(max(len(row) for row in rows), 5)
                table_data = []
                for row_values in rows:
                    normalized = (row_values + [''] * max_cols)[:max_cols]
                    table_data.append([
                        Paragraph(_analytics_inline_markdown_to_reportlab(value), styles['ReportSmall'])
                        for value in normalized
                    ])
                table = Table(table_data, repeatRows=1)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eaf2ff')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#123d71')),
                    ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d8e2ef')),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(table)
                story.append(Spacer(1, 8))
            continue

        heading_match = re.match(r'^(#{1,4})\s+(.+)$', stripped)
        if heading_match:
            level = len(heading_match.group(1))
            style_name = 'ReportH2' if level <= 2 else 'ReportH3'
            story.append(Paragraph(_analytics_inline_markdown_to_reportlab(heading_match.group(2)), styles[style_name]))
            idx += 1
            continue

        bullet_items = []
        while idx < len(lines):
            bullet_match = re.match(r'^\s*[-*]\s+(.+)$', lines[idx])
            if not bullet_match:
                break
            bullet_items.append(ListItem(
                Paragraph(_analytics_inline_markdown_to_reportlab(bullet_match.group(1)), styles['ReportBody']),
                leftIndent=10,
            ))
            idx += 1
        if bullet_items:
            story.append(ListFlowable(bullet_items, bulletType='bullet', start='circle', leftIndent=14, bulletFontName=base_font))
            story.append(Spacer(1, 3))
            continue

        ordered_items = []
        while idx < len(lines):
            ordered_match = re.match(r'^\s*\d+\.\s+(.+)$', lines[idx])
            if not ordered_match:
                break
            ordered_items.append(ListItem(
                Paragraph(_analytics_inline_markdown_to_reportlab(ordered_match.group(1)), styles['ReportBody']),
                leftIndent=10,
            ))
            idx += 1
        if ordered_items:
            story.append(ListFlowable(ordered_items, bulletType='1', leftIndent=14, bulletFontName=base_font))
            story.append(Spacer(1, 3))
            continue

        paragraph_lines = [stripped]
        idx += 1
        while idx < len(lines):
            next_line = lines[idx].strip()
            if (
                not next_line
                or next_line.startswith('#')
                or re.match(r'^\s*[-*]\s+', lines[idx])
                or re.match(r'^\s*\d+\.\s+', lines[idx])
                or (('|' in next_line) and idx + 1 < len(lines) and re.search(r'\|\s*:?-{3,}:?\s*\|', lines[idx + 1]))
            ):
                break
            paragraph_lines.append(next_line)
            idx += 1
        paragraph = ' '.join(paragraph_lines)
        story.append(Paragraph(_analytics_inline_markdown_to_reportlab(paragraph), styles['ReportBody']))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        '数据说明：本报告基于站内埋点聚合数据生成，PDF 不包含原始 IP、访客 ID 或会话 ID。',
        styles['ReportSmall'],
    ))

    def _draw_page(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont(base_font, 8)
        canvas.setFillColor(colors.HexColor('#94a3b8'))
        canvas.drawString(18 * mm, 10 * mm, '元芯传感网站运营报告')
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f'第 {doc_obj.page} 页')
        canvas.restoreState()

    doc.build(story, onFirstPage=_draw_page, onLaterPages=_draw_page)
    buffer.seek(0)
    return buffer


def build_site_analytics_report(range_days=30, start_date=None, end_date=None, granularity='day'):
    start_date_raw = str(start_date or '').strip()
    end_date_raw = str(end_date or '').strip()
    granularity_key = str(granularity or 'day').strip().lower() or 'day'

    if start_date_raw or end_date_raw:
        if not start_date_raw or not end_date_raw:
            raise ValueError('开始日期和结束日期必须同时填写')
        if granularity_key not in {'year', 'quarter', 'month', 'week', 'day'}:
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


SITE_ANALYTICS_AI_SYSTEM_PROMPT = """你是企业官网运营数据分析师，负责基于后台统计数据撰写中文网站运营报告。

要求：
1. 只使用用户提供的聚合数据，不要编造未提供的渠道、客户身份、订单或收入。
2. 报告要面向经营和营销决策，覆盖流量规模、访客质量、渠道来源、设备/系统、地域分布、热门内容、行为事件、转化表现和环比变化。
3. 明确指出数据采集口径限制：统计来自站内埋点，可能包含爬虫或测试访问；没有收入、订单、客户姓名、手机号等业务成交数据。
4. 输出结构：标题、核心结论、关键指标与环比、流量与渠道分析、内容与行为分析、地域/设备洞察、风险与异常、下阶段行动建议。
5. 行动建议要具体，可执行，适合 B2B 传感器官网运营。
6. 使用中文，专业、清晰，避免营销套话。
7. 标题与小标题使用正式书面语，例如“简要总结”“当前需重点关注”“核心观察”；不要使用面向个人称呼或过度口语化、不适合正式汇报的表述。
"""


def _site_report_get_ai_config():
    try:
        config = _site_report_get_config_fn() or {}
    except Exception:
        config = {}
    groups = (
        ('site_report', 'site_report_ai_api_key', 'site_report_ai_api_base', 'site_report_ai_model'),
        ('product_ai', 'product_ai_api_key', 'product_ai_api_base', 'product_ai_model'),
        ('chatbot', 'chatbot_api_key', 'chatbot_api_base', 'chatbot_model'),
    )
    selected = None
    for source, key_name, base_name, model_name in groups:
        api_key = str(config.get(key_name) or '').strip()
        if api_key:
            selected = (source, api_key, base_name, model_name)
            break
    if selected:
        source, api_key, base_name, model_name = selected
        api_base = str(config.get(base_name) or '').strip() or 'https://api.openai.com/v1'
        model = str(config.get(model_name) or '').strip() or 'gpt-4o-mini'
    else:
        source = ''
        api_key = ''
        api_base = 'https://api.openai.com/v1'
        model = 'gpt-4o-mini'
    try:
        max_tokens = int(config.get('site_report_ai_max_tokens') or SITE_ANALYTICS_AI_DEFAULT_MAX_TOKENS)
    except Exception:
        max_tokens = SITE_ANALYTICS_AI_DEFAULT_MAX_TOKENS
    max_tokens = max(256, min(max_tokens, 8000))
    try:
        temperature = float(config.get('site_report_ai_temperature') or SITE_ANALYTICS_AI_DEFAULT_TEMPERATURE)
    except Exception:
        temperature = SITE_ANALYTICS_AI_DEFAULT_TEMPERATURE
    temperature = max(0.0, min(temperature, 1.5))
    return {
        'api_key': api_key,
        'api_base': api_base,
        'model': model,
        'source': source,
        'max_tokens': max_tokens,
        'temperature': temperature,
    }


def _analytics_extract_chat_completion_text(result) -> str:
    if not isinstance(result, dict):
        return ''
    choices = result.get('choices') or []
    if not choices:
        return ''
    message = choices[0].get('message') or {}
    content = message.get('content', '')
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get('text')
                if isinstance(text, str):
                    parts.append(text)
        return ''.join(parts).strip()
    return ''


def _site_report_ai_result(text=None, error=None, error_type=None, model='', status_code=None):
    result = {
        'text': text,
        'error': error,
        'error_type': error_type,
        'model': model,
    }
    if status_code is not None:
        result['status_code'] = status_code
    return result


def _call_site_report_ai(messages):
    config = _site_report_get_ai_config()
    model = config.get('model', '')
    if not config.get('api_key'):
        return _site_report_ai_result(
            error='AI API Key 未配置。请先在后台「AI 与知识库」或专用网站报告 AI 配置中填写 API Key。',
            error_type='config',
            model=model,
        )

    has_requests = _site_report_requests_support and _site_report_requests_module is not None
    has_httpx = _site_report_httpx_support and _site_report_httpx_module is not None
    if not (has_requests or has_httpx):
        return _site_report_ai_result(
            error='缺少 HTTP 客户端库（requests/httpx），暂时无法调用 AI API。',
            error_type='dependency',
            model=model,
        )

    api_url = config['api_base'].rstrip('/') + '/chat/completions'
    headers = {
        'Authorization': f"Bearer {config['api_key']}",
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model,
        'messages': messages,
        'stream': False,
        'temperature': config.get('temperature', SITE_ANALYTICS_AI_DEFAULT_TEMPERATURE),
        'max_tokens': config.get('max_tokens', SITE_ANALYTICS_AI_DEFAULT_MAX_TOKENS),
    }
    connect_timeout = 20
    read_timeout = 300
    last_error = None
    for attempt in range(2):
        try:
            if has_requests:
                response = _site_report_requests_module.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=(connect_timeout, read_timeout),
                )
            else:
                timeout_obj = _site_report_httpx_module.Timeout(
                    connect=connect_timeout,
                    read=read_timeout,
                    write=60,
                    pool=60,
                )
                response = _site_report_httpx_module.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout_obj,
                )
            if response.status_code != 200:
                detail = (response.text or '').strip()[:500]
                message = f"AI API 错误: {response.status_code}{(' - ' + detail) if detail else ''}"
                last_error = _site_report_ai_result(
                    error=message,
                    error_type='upstream',
                    model=model,
                    status_code=response.status_code,
                )
                if attempt == 0 and (response.status_code == 429 or response.status_code >= 500):
                    time.sleep(1.5)
                    continue
                return last_error
            text = _analytics_extract_chat_completion_text(response.json())
            if text:
                return _site_report_ai_result(text=text, model=model)
            return _site_report_ai_result(
                error='AI API 返回格式错误',
                error_type='format',
                model=model,
            )
        except Exception as exc:
            last_error = _site_report_ai_result(
                error=f'AI API 调用失败: {str(exc)}',
                error_type='network',
                model=model,
            )
            if attempt == 0:
                time.sleep(1.5)
                continue
            return last_error
    return last_error or _site_report_ai_result(
        error='AI API 调用失败',
        error_type='network',
        model=model,
    )


def _analytics_top_rows(rows, limit=8):
    if not isinstance(rows, list):
        return []
    return rows[:max(1, int(limit or 8))]


def _analytics_summary_metric(report, key: str):
    summary = report.get('summary') if isinstance(report, dict) else {}
    if not isinstance(summary, dict):
        return 0
    value = summary.get(key, 0)
    try:
        return float(value)
    except Exception:
        return 0.0


def _analytics_compare_metric(current_value, previous_value, *, digits=2):
    current_num = round(float(current_value or 0), digits)
    previous_num = round(float(previous_value or 0), digits)
    delta = round(current_num - previous_num, digits)
    if previous_num == 0:
        change_rate = None if current_num else 0.0
    else:
        change_rate = round((delta / previous_num) * 100.0, 2)
    return {
        'current': current_num,
        'previous': previous_num,
        'change': delta,
        'change_rate': change_rate,
    }


def _analytics_build_comparison(current_report, previous_report):
    metric_defs = (
        ('pageviews', '页面浏览量(PV)', 0),
        ('unique_visitors', '独立访客(UV)', 0),
        ('sessions', '会话数', 0),
        ('avg_session_duration_sec', '平均会话时长(秒)', 2),
        ('bounce_rate', '跳出率(百分点)', 2),
        ('conversion_events', '转化事件', 0),
        ('conversion_sessions', '转化会话', 0),
        ('conversion_rate', '转化率(百分点)', 2),
    )
    output = {}
    for key, label, digits in metric_defs:
        output[key] = {
            'label': label,
            **_analytics_compare_metric(
                _analytics_summary_metric(current_report, key),
                _analytics_summary_metric(previous_report, key),
                digits=digits,
            ),
        }
    return output


def _analytics_compact_report_for_ai(report):
    safe = report if isinstance(report, dict) else {}
    return {
        'range_label': safe.get('range_label', ''),
        'start_date': safe.get('start_date', ''),
        'end_date': safe.get('end_date', ''),
        'granularity': safe.get('granularity', ''),
        'summary': safe.get('summary') if isinstance(safe.get('summary'), dict) else {},
        'trend': _analytics_top_rows(safe.get('trend'), 80),
        'source_breakdown': _analytics_top_rows(safe.get('source_breakdown'), 8),
        'device_breakdown': _analytics_top_rows(safe.get('device_breakdown'), 8),
        'os_breakdown': _analytics_top_rows(safe.get('os_breakdown'), 8),
        'province_breakdown': _analytics_top_rows(safe.get('province_breakdown'), 10),
        'continent_breakdown': _analytics_top_rows(safe.get('continent_breakdown'), 8),
        'country_breakdown': _analytics_top_rows(safe.get('country_breakdown'), 10),
        'top_pages': _analytics_top_rows(safe.get('top_pages'), 12),
        'top_events': _analytics_top_rows(safe.get('top_events'), 12),
    }


def build_site_analytics_ai_report_context(period='month', anchor_date=None):
    period_key = str(period or 'month').strip().lower()
    if period_key not in {'week', 'month', 'quarter', 'year'}:
        raise ValueError('报告周期无效')

    anchor_raw = str(anchor_date or '').strip()
    anchor_value = _analytics_parse_local_date(anchor_raw) if anchor_raw else None
    today = datetime.now(BEIJING_TZ).date()
    if anchor_raw and anchor_value is None:
        raise ValueError('anchor_date 格式无效，必须为 YYYY-MM-DD')
    if anchor_value is None:
        anchor_value = today
    if anchor_value > today:
        raise ValueError('anchor_date 不能晚于今天')

    current_start, current_full_end = _analytics_period_bounds(period_key, anchor_value)
    current_end = min(anchor_value, current_full_end)
    elapsed_days = max(0, (current_end - current_start).days)
    previous_start, previous_full_end = _analytics_previous_period_bounds(
        period_key,
        current_start,
        current_full_end,
    )
    previous_end = min(previous_start + timedelta(days=elapsed_days), previous_full_end)

    granularity = _analytics_report_period_granularity(period_key)
    current_report = build_site_analytics_report(
        start_date=_analytics_format_local_date(current_start),
        end_date=_analytics_format_local_date(current_end),
        granularity=granularity,
    )
    previous_report = build_site_analytics_report(
        start_date=_analytics_format_local_date(previous_start),
        end_date=_analytics_format_local_date(previous_end),
        granularity=granularity,
    )

    period_label = _analytics_report_period_label(period_key)
    return {
        'period': period_key,
        'period_label': period_label,
        'anchor_date': _analytics_format_local_date(anchor_value),
        'current_range': {
            'start_date': _analytics_format_local_date(current_start),
            'end_date': _analytics_format_local_date(current_end),
            'label': f"{_analytics_format_local_date(current_start)} 至 {_analytics_format_local_date(current_end)} · {period_label}",
        },
        'previous_range': {
            'start_date': _analytics_format_local_date(previous_start),
            'end_date': _analytics_format_local_date(previous_end),
            'label': f"{_analytics_format_local_date(previous_start)} 至 {_analytics_format_local_date(previous_end)} · 上一周期",
        },
        'comparison': _analytics_build_comparison(current_report, previous_report),
        'current': _analytics_compact_report_for_ai(current_report),
        'previous': _analytics_compact_report_for_ai(previous_report),
    }


def _build_site_analytics_ai_messages(context):
    compact_json = json.dumps(context, ensure_ascii=False, separators=(',', ':'))
    user_prompt = (
        '请基于以下官网运营统计数据生成详细网站运营报告。'
        '数据均为聚合口径，不能反推出个人身份；请重点分析当前周期与上一周期的环比变化。'
        '\n\n'
        f'{compact_json}'
    )
    return [
        {'role': 'system', 'content': SITE_ANALYTICS_AI_SYSTEM_PROMPT},
        {'role': 'user', 'content': user_prompt},
    ]


def _site_report_ai_job_path(job_id: str) -> Path:
    safe_id = _analytics_report_safe_id(job_id)
    return SITE_ANALYTICS_AI_JOBS_DIR / f'{safe_id}.json'


def _site_report_ai_now_text():
    return datetime.now(BEIJING_TZ).isoformat(timespec='seconds')


def _read_site_report_ai_job(job_id: str):
    safe_id = _analytics_report_safe_id(job_id)
    if not safe_id:
        return None
    job = _analytics_read_json_file(_site_report_ai_job_path(safe_id), default=None)
    return job if isinstance(job, dict) else None


def _write_site_report_ai_job(job_id: str, updates):
    safe_id = _analytics_report_safe_id(job_id)
    if not safe_id:
        return None
    with SITE_ANALYTICS_AI_JOBS_LOCK:
        existing = _read_site_report_ai_job(safe_id) or {}
        next_job = dict(existing)
        next_job.update(updates if isinstance(updates, dict) else {})
        next_job['id'] = safe_id
        next_job['updated_at'] = _site_report_ai_now_text()
        try:
            next_job['progress'] = max(0, min(100, int(next_job.get('progress') or 0)))
        except Exception:
            next_job['progress'] = 0
        _analytics_write_json_file(_site_report_ai_job_path(safe_id), next_job)
        return next_job


def _site_report_ai_job_public(job):
    safe = job if isinstance(job, dict) else {}
    output = {
        'id': _analytics_report_safe_id(safe.get('id')),
        'status': _analytics_clean_text(safe.get('status'), max_length=24) or 'unknown',
        'progress': max(0, min(100, _analytics_to_int(safe.get('progress'), default=0))),
        'message': _analytics_clean_text(safe.get('message'), max_length=160),
        'created_at': _analytics_clean_text(safe.get('created_at'), max_length=40),
        'updated_at': _analytics_clean_text(safe.get('updated_at'), max_length=40),
        'period': _analytics_clean_text(safe.get('period'), max_length=20),
        'anchor_date': _analytics_clean_text(safe.get('anchor_date'), max_length=10),
    }
    if isinstance(safe.get('result'), dict):
        output['result'] = safe.get('result')
    if safe.get('error'):
        output['error'] = _analytics_clean_text(safe.get('error'), max_length=500)
        output['error_type'] = _analytics_clean_text(safe.get('error_type'), max_length=40)
    return output


def _build_site_report_ai_success_payload(report_text, context, model, generated_at, public_record):
    safe_context = context if isinstance(context, dict) else {}
    current = safe_context.get('current') if isinstance(safe_context.get('current'), dict) else {}
    return {
        'success': True,
        'report': str(report_text or '').strip(),
        'generated_at': generated_at,
        'model': model,
        'period': safe_context.get('period'),
        'period_label': safe_context.get('period_label'),
        'anchor_date': safe_context.get('anchor_date'),
        'current_range': safe_context.get('current_range') if isinstance(safe_context.get('current_range'), dict) else {},
        'previous_range': safe_context.get('previous_range') if isinstance(safe_context.get('previous_range'), dict) else {},
        'comparison': safe_context.get('comparison') if isinstance(safe_context.get('comparison'), dict) else {},
        'current_summary': current.get('summary') if isinstance(current.get('summary'), dict) else {},
        'report_record': public_record,
        'report_id': public_record.get('id') if isinstance(public_record, dict) else '',
        'download_url': public_record.get('download_url') if isinstance(public_record, dict) else '',
    }


def _cleanup_old_site_report_ai_jobs():
    try:
        SITE_ANALYTICS_AI_JOBS_DIR.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - 7 * 24 * 3600
        for path in SITE_ANALYTICS_AI_JOBS_DIR.glob('*.json'):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except Exception:
                pass
    except Exception:
        pass


def _run_site_report_ai_generation_job(app_obj, job_id, period, anchor_date, generation_lock):
    def update(status, progress, message, **extra):
        payload = {
            'status': status,
            'progress': progress,
            'message': message,
        }
        payload.update(extra)
        _write_site_report_ai_job(job_id, payload)

    def run_inner():
        try:
            update('running', 15, '正在准备统计数据...')
            context = build_site_analytics_ai_report_context(period=period, anchor_date=anchor_date)
            update('running', 35, '正在构建环比分析上下文...')
            messages = _build_site_analytics_ai_messages(context)
            update('running', 55, '正在调用 AI 生成报告...')
            ai_result = _call_site_report_ai(messages)
            if ai_result.get('error'):
                update(
                    'failed',
                    100,
                    ai_result.get('error') or 'AI 报告生成失败',
                    error=ai_result.get('error') or 'AI 报告生成失败',
                    error_type=ai_result.get('error_type') or 'unknown',
                )
                return
            report_text = str(ai_result.get('text') or '').strip()
            update('running', 85, '正在保存报告...')
            ai_config = _site_report_get_ai_config()
            generated_at = datetime.now(BEIJING_TZ).isoformat(timespec='seconds')
            saved_record = _append_site_analytics_ai_report_record(
                _build_site_analytics_ai_report_record(
                    report_text=report_text,
                    context=context,
                    model=ai_result.get('model') or ai_config.get('model', ''),
                    generated_at=generated_at,
                )
            )
            public_record = _analytics_public_ai_report_row(saved_record)
            result = _build_site_report_ai_success_payload(
                report_text,
                context,
                ai_result.get('model') or ai_config.get('model', ''),
                generated_at,
                public_record,
            )
            update('succeeded', 100, 'AI 报告已生成', result=result)
        except Exception as exc:
            LOGGER.exception('Site analytics AI report generation job failed.')
            update(
                'failed',
                100,
                f'AI 报告生成失败: {str(exc)}',
                error=f'AI 报告生成失败: {str(exc)}',
                error_type='internal',
            )
        finally:
            generation_lock.release()

    if app_obj is not None:
        with app_obj.app_context():
            run_inner()
    else:
        run_inner()


# ─────────────────────────────────────────────────────────────────────
# 定时报告生成调度
# ─────────────────────────────────────────────────────────────────────

def _load_scheduled_report_state():
    """读取定时报告生成状态文件。"""
    if not SCHEDULED_REPORTS_STATE_FILE.exists():
        return {'generated': []}
    try:
        data = json.loads(SCHEDULED_REPORTS_STATE_FILE.read_text(encoding='utf-8'))
        if isinstance(data, dict) and isinstance(data.get('generated'), list):
            return data
    except Exception:
        pass
    return {'generated': []}


def _save_scheduled_report_state(state):
    """原子写入定时报告生成状态文件。"""
    SCHEDULED_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    # 保留最近 200 条记录
    generated = state.get('generated', [])
    if len(generated) > 200:
        generated = generated[-200:]
        state['generated'] = generated
    tmp = SCHEDULED_REPORTS_STATE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(SCHEDULED_REPORTS_STATE_FILE)


def _already_generated(state, report_type, period_start, period_end):
    """检查指定周期是否已生成过报告。"""
    for entry in state.get('generated', []):
        if (entry.get('type') == report_type
                and entry.get('period_start') == period_start
                and entry.get('period_end') == period_end):
            return True
    return False


def _get_failure_count(state, report_type, period_start, period_end):
    """获取指定周期的连续失败次数。"""
    for entry in state.get('generated', []):
        if (entry.get('type') == report_type
                and entry.get('period_start') == period_start
                and entry.get('period_end') == period_end):
            return entry.get('failure_count', 0)
    return 0


def _record_generation(state, report_type, period_start, period_end, report_id):
    """记录一次成功的报告生成。"""
    state.setdefault('generated', []).append({
        'type': report_type,
        'period_start': period_start,
        'period_end': period_end,
        'report_id': report_id,
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'email_sent': False,
        'email_sent_at': None,
        'failure_count': 0,
    })


def _record_generation_failure(state, report_type, period_start, period_end):
    """记录一次报告生成失败。"""
    for entry in state.get('generated', []):
        if (entry.get('type') == report_type
                and entry.get('period_start') == period_start
                and entry.get('period_end') == period_end):
            entry['failure_count'] = entry.get('failure_count', 0) + 1
            return
    state.setdefault('generated', []).append({
        'type': report_type,
        'period_start': period_start,
        'period_end': period_end,
        'report_id': None,
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'email_sent': False,
        'email_sent_at': None,
        'failure_count': 1,
    })


def _record_email_sent(state, report_type, period_start, period_end):
    """记录邮件推送成功。"""
    for entry in state.get('generated', []):
        if (entry.get('type') == report_type
                and entry.get('period_start') == period_start
                and entry.get('period_end') == period_end):
            entry['email_sent'] = True
            entry['email_sent_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
            return


def _compute_due_period(report_type, now_beijing):
    """
    根据报告类型和当前北京时间，计算当前应当生成的上一周期范围。
    返回 (period_start_str, period_end_str, api_period_key, anchor_date_str) 或 None。
    """
    import calendar as _cal
    today = now_beijing.date()
    weekday = today.weekday()  # 0=Monday

    if report_type == 'weekly':
        # 仅在周一触发，生成上周 Mon-Sun 的报告
        if weekday != 0:
            return None
        last_monday = today - timedelta(days=7)
        last_sunday = last_monday + timedelta(days=6)
        return (
            last_monday.isoformat(),
            last_sunday.isoformat(),
            'week',
            last_sunday.isoformat(),
        )

    if report_type == 'monthly':
        # 在每月 1-3 号触发，生成上月整月报告（3 天宽限期）
        if today.day > 3:
            return None
        first_of_this_month = today.replace(day=1)
        last_day_prev = first_of_this_month - timedelta(days=1)
        first_day_prev = last_day_prev.replace(day=1)
        return (
            first_day_prev.isoformat(),
            last_day_prev.isoformat(),
            'month',
            last_day_prev.isoformat(),
        )

    if report_type == 'yearly':
        # 在每年 1 月 1-3 号触发，生成上年整年报告
        if today.month != 1 or today.day > 3:
            return None
        prev_year = today.year - 1
        return (
            f'{prev_year}-01-01',
            f'{prev_year}-12-31',
            'year',
            f'{prev_year}-12-31',
        )

    return None


def _generate_scheduled_report(app_obj, period_key, anchor_date):
    """
    桥接现有报告生成逻辑：同步调用 AI 生成并保存报告，返回 report_id 或 None。
    """
    try:
        generation_lock = _AnalyticsFileLock(
            SITE_ANALYTICS_AI_GENERATION_LOCK_FILE,
            ttl_seconds=SITE_ANALYTICS_AI_JOB_LOCK_TTL_SECONDS,
            metadata={'source': 'scheduled'},
        )
        if not generation_lock.acquire():
            LOGGER.warning('[ScheduledReport] Cannot acquire generation lock, skipping.')
            return None
        try:
            with app_obj.app_context():
                context = build_site_analytics_ai_report_context(
                    period=period_key, anchor_date=anchor_date
                )
                messages = _build_site_analytics_ai_messages(context)
                ai_result = _call_site_report_ai(messages)
                if ai_result.get('error'):
                    LOGGER.error('[ScheduledReport] AI error: %s', ai_result.get('error'))
                    return None
                report_text = str(ai_result.get('text') or '').strip()
                ai_config = _site_report_get_ai_config()
                generated_at = datetime.now(BEIJING_TZ).isoformat(timespec='seconds')
                saved_record = _append_site_analytics_ai_report_record(
                    _build_site_analytics_ai_report_record(
                        report_text=report_text,
                        context=context,
                        model=ai_result.get('model') or ai_config.get('model', ''),
                        generated_at=generated_at,
                    )
                )
                report_id = saved_record.get('id')
                # 尝试生成 PDF
                try:
                    _generate_site_analytics_ai_report_pdf(saved_record)
                except Exception:
                    LOGGER.warning('[ScheduledReport] PDF generation failed, report saved without PDF.', exc_info=True)
                LOGGER.info('[ScheduledReport] Report generated: %s (%s)', report_id, period_key)
                return report_id
        finally:
            generation_lock.release()
    except Exception:
        LOGGER.exception('[ScheduledReport] Unexpected error during scheduled generation.')
        return None


def _send_scheduled_report_emails(app_obj, report_id, recipient_emails):
    """为定时生成的报告发送邮件推送。"""
    try:
        from app.routes.admin import (
            _send_smtp_mail,
            _get_email_auth_settings,
        )
    except ImportError:
        LOGGER.warning('[ScheduledReport] Cannot import email helpers from admin module.')
        return False

    record = _get_site_analytics_ai_report_record(report_id)
    if not record:
        LOGGER.warning('[ScheduledReport] Report %s not found for email push.', report_id)
        return False

    with app_obj.app_context():
        config = _site_report_get_config_fn()
        smtp_settings = _get_email_auth_settings(config)
        if not smtp_settings.get('configured'):
            LOGGER.info('[ScheduledReport] SMTP not configured, skipping email push.')
            return False

        title = _analytics_ai_report_title(record) or 'AI 网站运营报告'
        period_label = record.get('period_label', '')
        current_range = record.get('current_range', {}) if isinstance(record.get('current_range'), dict) else {}
        range_label = f"{current_range.get('start_date', '')} ~ {current_range.get('end_date', '')}"

        # 构建 HTML 邮件正文
        html_body = (
            f'<div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;">'
            f'<h2 style="color:#123d71;">{html.escape(title)}</h2>'
            f'<p style="color:#333;">报告周期：{html.escape(range_label)}</p>'
            f'<p style="color:#333;">报告已由系统自动生成，详情请登录管理后台查看。</p>'
            f'<hr style="border:none;border-top:1px solid #eee;margin:20px 0;">'
            f'<p style="color:#999;font-size:12px;">此邮件由定时报告系统自动发送。</p>'
            f'</div>'
        )
        text_body = f'{title}\n报告周期：{range_label}\n报告已由系统自动生成，详情请登录管理后台查看。'

        # 尝试获取 PDF 附件
        pdf_path = _analytics_report_pdf_cache_path(report_id)
        attachments = None
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            pdf_data = pdf_path.read_bytes()
            pdf_filename = f'{_analytics_report_filename_part(period_label, fallback="report")}.pdf'
            attachments = [(pdf_filename, pdf_data, 'application/pdf')]

        sent_count = 0
        for email_addr in recipient_emails:
            try:
                _send_smtp_mail(
                    smtp_settings,
                    to_email=email_addr,
                    subject=f'[网站运营报告] {title}',
                    html_body=html_body,
                    text_body=text_body,
                    attachments=attachments,
                )
                sent_count += 1
                LOGGER.info('[ScheduledReport] Email sent to %s', email_addr)
            except Exception:
                LOGGER.warning('[ScheduledReport] Failed to send email to %s', email_addr, exc_info=True)

        return sent_count > 0


def _scheduled_report_loop(app_obj, get_config_fn, update_config_fn, data_dir):
    """定时报告调度主循环，在 daemon thread 中运行。"""
    LOGGER.info('[ScheduledReport] Scheduler thread started.')
    while True:
        time.sleep(SCHEDULED_REPORT_CHECK_INTERVAL)
        try:
            # 获取调度器文件锁，防止多 worker 并发
            scheduler_lock = _AnalyticsFileLock(
                SCHEDULED_REPORTS_LOCK_FILE,
                ttl_seconds=SCHEDULED_REPORT_LOCK_TTL,
                metadata={'source': 'scheduler'},
            )
            if not scheduler_lock.acquire():
                continue
        except Exception:
            continue

        try:
            config = get_config_fn()
            sched_cfg = config.get('scheduled_reports', {})
            if not sched_cfg.get('enabled', False):
                continue

            now_beijing = datetime.now(BEIJING_TZ)
            if now_beijing.hour < SCHEDULED_REPORT_GENERATE_HOUR_BEIJING:
                continue

            state = _load_scheduled_report_state()

            for report_type in ('weekly', 'monthly', 'yearly'):
                if not sched_cfg.get(report_type, True):
                    continue

                due = _compute_due_period(report_type, now_beijing)
                if not due:
                    continue
                period_start, period_end, api_period, anchor_date = due

                if _already_generated(state, report_type, period_start, period_end):
                    # 检查是否需要补发邮件
                    for entry in state.get('generated', []):
                        if (entry.get('type') == report_type
                                and entry.get('period_start') == period_start
                                and entry.get('period_end') == period_end
                                and not entry.get('email_sent')
                                and entry.get('report_id')):
                            email_cfg = config.get('report_email_push', {})
                            if email_cfg.get('enabled') and email_cfg.get('recipient_emails'):
                                ok = _send_scheduled_report_emails(
                                    app_obj, entry['report_id'], email_cfg['recipient_emails']
                                )
                                if ok:
                                    _record_email_sent(state, report_type, period_start, period_end)
                                    _save_scheduled_report_state(state)
                    continue

                # 检查失败次数
                if _get_failure_count(state, report_type, period_start, period_end) >= SCHEDULED_REPORT_MAX_FAILURES:
                    continue

                # 生成报告
                report_id = _generate_scheduled_report(app_obj, api_period, anchor_date)
                if report_id:
                    _record_generation(state, report_type, period_start, period_end, report_id)

                    # 邮件推送
                    email_cfg = config.get('report_email_push', {})
                    if email_cfg.get('enabled') and email_cfg.get('recipient_emails'):
                        ok = _send_scheduled_report_emails(
                            app_obj, report_id, email_cfg['recipient_emails']
                        )
                        if ok:
                            _record_email_sent(state, report_type, period_start, period_end)

                    _save_scheduled_report_state(state)
                else:
                    _record_generation_failure(state, report_type, period_start, period_end)
                    _save_scheduled_report_state(state)
        except Exception:
            LOGGER.exception('[ScheduledReport] Scheduler loop error.')
        finally:
            try:
                scheduler_lock.release()
            except Exception:
                pass


def _start_scheduled_report_worker_once(app, get_config_fn, update_config_fn, data_dir):
    """确保调度线程只启动一次。"""
    if getattr(app, '_scheduled_report_worker_started', False):
        return
    with _SCHEDULED_REPORT_THREAD_LOCK:
        if getattr(app, '_scheduled_report_worker_started', False):
            return
        thread = threading.Thread(
            target=_scheduled_report_loop,
            args=(app, get_config_fn, update_config_fn, data_dir),
            name='site-report-scheduler',
            daemon=True,
        )
        thread.start()
        app._scheduled_report_worker_started = True
        LOGGER.info('[ScheduledReport] Worker thread started.')


def register_site_analytics_routes(
    app,
    *,
    login_required,
    data_dir,
    get_client_ip,
    resolve_ip_location,
    beijing_tz,
    get_config=None,
    update_config=None,
    requests_support=False,
    requests_module=None,
    httpx_support=False,
    httpx_module=None,
):
    """注册公开埋点收集与后台统计报表相关路由。"""
    global SITE_ANALYTICS_LOG_FILE, SITE_ANALYTICS_AI_REPORTS_FILE, SITE_ANALYTICS_AI_REPORTS_DIR
    global SITE_ANALYTICS_AI_REPORTS_INDEX_FILE, SITE_ANALYTICS_AI_REPORTS_PDF_DIR, SITE_ANALYTICS_AI_JOBS_DIR
    global SITE_ANALYTICS_AI_GENERATION_LOCK_FILE, SITE_ANALYTICS_AI_PDF_LOCK_FILE, BEIJING_TZ, _resolve_ip_location_fn
    global _site_report_get_config_fn, _site_report_requests_support, _site_report_requests_module
    global _site_report_httpx_support, _site_report_httpx_module, _site_report_update_config_fn

    SITE_ANALYTICS_LOG_FILE = Path(data_dir) / "site_analytics_events.jsonl"
    SITE_ANALYTICS_AI_REPORTS_FILE = Path(data_dir) / "site_analytics_ai_reports.jsonl"
    SITE_ANALYTICS_AI_REPORTS_DIR = Path(data_dir) / "site_analytics_ai_reports"
    SITE_ANALYTICS_AI_REPORTS_INDEX_FILE = SITE_ANALYTICS_AI_REPORTS_DIR / "index.json"
    SITE_ANALYTICS_AI_REPORTS_PDF_DIR = SITE_ANALYTICS_AI_REPORTS_DIR / "pdf_cache"
    SITE_ANALYTICS_AI_JOBS_DIR = Path(data_dir) / "site_analytics_ai_jobs"
    SITE_ANALYTICS_AI_GENERATION_LOCK_FILE = Path(data_dir) / "site_analytics_ai_report_generation.lock"
    SITE_ANALYTICS_AI_PDF_LOCK_FILE = Path(data_dir) / "site_analytics_ai_report_pdf.lock"
    BEIJING_TZ = beijing_tz or BEIJING_TZ
    _resolve_ip_location_fn = resolve_ip_location
    _site_report_get_config_fn = get_config if callable(get_config) else (lambda: {})
    _site_report_requests_support = bool(requests_support and requests_module is not None)
    _site_report_requests_module = requests_module if _site_report_requests_support else None
    _site_report_httpx_support = bool(httpx_support and httpx_module is not None)
    _site_report_httpx_module = httpx_module if _site_report_httpx_support else None
    _site_report_update_config_fn = update_config if callable(update_config) else None

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
        denied = _require_site_reports_admin_api()
        if denied:
            return denied
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

    @app.route('/api/admin/site-reports/ai-reports', methods=['GET'])
    @login_required
    def list_site_report_ai_reports_admin():
        denied = _require_site_reports_admin_api()
        if denied:
            return denied
        """获取已生成的 AI 网站运营报告清单。"""
        period = _analytics_clean_text(request.args.get('period') or '', max_length=20).lower()
        if period and period not in {'week', 'month', 'quarter', 'year'}:
            return jsonify({'success': False, 'message': '报告周期无效'}), 400
        try:
            limit = int(request.args.get('limit') or 80)
        except Exception:
            limit = 80
        limit = min(max(limit, 1), 200)
        records = _iter_site_analytics_ai_report_records()
        if period:
            records = [item for item in records if item.get('period') == period]
        reports = [_analytics_public_ai_report_row(item) for item in records[:limit]]
        grouped = {
            'year': [],
            'quarter': [],
            'month': [],
            'week': [],
        }
        for item in reports:
            key = item.get('period')
            if key in grouped:
                grouped[key].append(item)
        return jsonify({
            'success': True,
            'reports': reports,
            'grouped': grouped,
            'total': len(reports),
        })

    @app.route('/api/admin/site-reports/ai-report', methods=['POST'])
    @login_required
    def generate_site_report_ai_admin():
        denied = _require_site_reports_admin_api()
        if denied:
            return denied
        """基于聚合统计与环比数据生成 AI 网站运营报告。"""
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            payload = {}
        period = _analytics_clean_text(payload.get('period') or 'month', max_length=20).lower()
        anchor_date = _analytics_clean_text(
            payload.get('anchor_date') or payload.get('end_date') or '',
            max_length=10,
        )
        if period not in {'week', 'month', 'quarter', 'year'}:
            return jsonify({'success': False, 'message': '报告周期无效'}), 400
        parsed_anchor = _analytics_parse_local_date(anchor_date) if anchor_date else None
        if anchor_date and parsed_anchor is None:
            return jsonify({'success': False, 'message': 'anchor_date 格式无效，必须为 YYYY-MM-DD'}), 400
        if parsed_anchor and parsed_anchor > datetime.now(BEIJING_TZ).date():
            return jsonify({'success': False, 'message': 'anchor_date 不能晚于今天'}), 400

        _cleanup_old_site_report_ai_jobs()
        job_id = uuid.uuid4().hex
        generation_lock = _AnalyticsFileLock(
            SITE_ANALYTICS_AI_GENERATION_LOCK_FILE,
            ttl_seconds=SITE_ANALYTICS_AI_JOB_LOCK_TTL_SECONDS,
            metadata={'type': 'site-report-ai-generation', 'job_id': job_id},
        )
        if not generation_lock.acquire():
            lock_meta = generation_lock.read_metadata()
            active_job = _read_site_report_ai_job(lock_meta.get('job_id') or '')
            return jsonify({
                'success': False,
                'message': 'AI 报告正在生成中，请稍后查看进度。',
                'job': _site_report_ai_job_public(active_job) if active_job else {
                    'id': _analytics_report_safe_id(lock_meta.get('job_id')),
                    'status': 'running',
                    'progress': 55,
                    'message': 'AI report generation is already running',
                },
            }), 409
        initial_job = _write_site_report_ai_job(job_id, {
            'status': 'queued',
            'progress': 5,
            'message': 'AI report queued',
            'created_at': _site_report_ai_now_text(),
            'period': period,
            'anchor_date': anchor_date,
        })
        try:
            app_obj = current_app._get_current_object()
        except Exception:
            app_obj = None
        try:
            worker = threading.Thread(
                target=_run_site_report_ai_generation_job,
                args=(app_obj, job_id, period, anchor_date, generation_lock),
                daemon=True,
            )
            worker.start()
        except Exception as exc:
            generation_lock.release()
            _write_site_report_ai_job(job_id, {
                'status': 'failed',
                'progress': 100,
                'message': f'Failed to start AI report job: {str(exc)}',
                'error': f'Failed to start AI report job: {str(exc)}',
                'error_type': 'internal',
            })
            return jsonify({'success': False, 'message': f'AI 报告任务启动失败: {str(exc)}'}), 500
        return jsonify({
            'success': True,
            'job_id': job_id,
            'status_url': f'/api/admin/site-reports/ai-report/jobs/{job_id}',
            'job': _site_report_ai_job_public(initial_job),
        }), 202

    @app.route('/api/admin/site-reports/ai-report/jobs/<job_id>', methods=['GET'])
    @login_required
    def get_site_report_ai_job_admin(job_id):
        denied = _require_site_reports_admin_api()
        if denied:
            return denied
        job = _read_site_report_ai_job(job_id)
        if not job:
            return jsonify({'success': False, 'message': 'AI 报告任务不存在或已过期'}), 404
        return jsonify({'success': True, 'job': _site_report_ai_job_public(job)})

    @app.route('/api/admin/site-reports/ai-reports/<report_id>', methods=['DELETE'])
    @login_required
    def delete_site_report_ai_report_admin(report_id):
        denied = _require_site_reports_admin_api()
        if denied:
            return denied
        if not _delete_site_analytics_ai_report_record(report_id):
            return jsonify({'success': False, 'message': '报告不存在或已被清理'}), 404
        return jsonify({'success': True})

    @app.route('/api/admin/site-reports/ai-reports/<report_id>/download', methods=['GET'])
    @login_required
    def download_site_report_ai_report_admin(report_id):
        denied = _require_site_reports_admin_api()
        if denied:
            return denied
        """下载渲染后的 AI 网站运营报告 PDF。"""
        record = _get_site_analytics_ai_report_record(report_id)
        if not record:
            return jsonify({'success': False, 'message': '报告不存在或已被清理'}), 404
        try:
            pdf_buffer = _generate_site_analytics_ai_report_pdf(record)
        except SiteAnalyticsBusyError as exc:
            return jsonify({'success': False, 'message': str(exc)}), 429
        except RuntimeError as exc:
            return jsonify({'success': False, 'message': str(exc)}), 503
        except Exception as exc:
            return jsonify({'success': False, 'message': f'PDF生成失败: {str(exc)}'}), 500
        filename = (
            _analytics_report_filename_part(record.get('period_label'), fallback='site-report')
            + '-'
            + _analytics_report_filename_part(record.get('title'), fallback=record.get('id') or 'report')
            + '.pdf'
        )
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename,
            max_age=0,
        )

    # ── 定时报告配置 API ──

    @app.route('/api/admin/scheduled-reports/config', methods=['GET'])
    @login_required
    def get_scheduled_reports_config():
        """获取定时报告配置和状态。"""
        denied = _require_site_reports_admin_api()
        if denied:
            return denied
        try:
            from app.routes.admin import _get_email_auth_settings, _load_admin_users

            config = _site_report_get_config_fn()
            sched_cfg = config.get('scheduled_reports', {})
            email_cfg = config.get('report_email_push', {})
            smtp_settings = _get_email_auth_settings(config)

            # 获取已验证邮箱的管理员列表
            admin_file = Path(__file__).resolve().parents[2] / 'data' / 'admin_users.json'
            users_data = _load_admin_users(admin_file)
            verified_emails = []
            for u in users_data.get('users', []):
                if u.get('email_verified') and u.get('email'):
                    verified_emails.append({
                        'email': u['email'],
                        'username': u.get('username', ''),
                    })

            # 最近生成记录
            state = _load_scheduled_report_state()
            recent = list(reversed(state.get('generated', [])))[:20]

            return jsonify({
                'success': True,
                'scheduled_reports': {
                    'enabled': bool(sched_cfg.get('enabled', False)),
                    'weekly': bool(sched_cfg.get('weekly', True)),
                    'monthly': bool(sched_cfg.get('monthly', True)),
                    'yearly': bool(sched_cfg.get('yearly', True)),
                },
                'report_email_push': {
                    'enabled': bool(email_cfg.get('enabled', False)),
                    'recipient_emails': list(email_cfg.get('recipient_emails', [])),
                },
                'smtp_configured': bool(smtp_settings.get('configured')),
                'verified_admin_emails': verified_emails,
                'recent_generations': recent,
            })
        except Exception as exc:
            return jsonify({'success': False, 'message': f'读取配置失败: {str(exc)}'}), 500

    @app.route('/api/admin/scheduled-reports/config', methods=['PUT'])
    @login_required
    def update_scheduled_reports_config():
        """更新定时报告和邮件推送配置。"""
        denied = _require_site_reports_admin_api()
        if denied:
            return denied
        if not callable(_site_report_update_config_fn):
            return jsonify({'success': False, 'message': '配置更新功能不可用'}), 503
        try:
            from app.routes.admin import _get_email_auth_settings, _load_admin_users

            payload = request.get_json(silent=True) or {}
            sched = payload.get('scheduled_reports', {})
            email_push = payload.get('report_email_push', {})

            # 校验邮件推送收件人
            recipient_emails = list(email_push.get('recipient_emails', []))
            if recipient_emails and email_push.get('enabled'):
                config = _site_report_get_config_fn()
                smtp_settings = _get_email_auth_settings(config)
                if not smtp_settings.get('configured'):
                    return jsonify({
                        'success': False,
                        'message': 'SMTP 未配置，请先在系统设置中配置 SMTP 后再开启邮件推送。',
                    }), 400

                admin_file = Path(__file__).resolve().parents[2] / 'data' / 'admin_users.json'
                users_data = _load_admin_users(admin_file)
                verified_set = {
                    u['email'] for u in users_data.get('users', [])
                    if u.get('email_verified') and u.get('email')
                }
                invalid = [e for e in recipient_emails if e not in verified_set]
                if invalid:
                    return jsonify({
                        'success': False,
                        'message': f'以下邮箱未验证或不存在: {", ".join(invalid)}',
                    }), 400

            new_config = {
                'scheduled_reports': {
                    'enabled': bool(sched.get('enabled', False)),
                    'weekly': bool(sched.get('weekly', True)),
                    'monthly': bool(sched.get('monthly', True)),
                    'yearly': bool(sched.get('yearly', True)),
                },
                'report_email_push': {
                    'enabled': bool(email_push.get('enabled', False)),
                    'recipient_emails': recipient_emails,
                },
            }
            _site_report_update_config_fn(new_config)
            return jsonify({'success': True, 'message': '定时报告设置已保存。'})
        except Exception as exc:
            return jsonify({'success': False, 'message': f'保存配置失败: {str(exc)}'}), 500

    @app.route('/api/admin/scheduled-reports/test-email', methods=['POST'])
    @login_required
    def send_scheduled_report_test_email():
        """发送测试邮件验证推送通道。"""
        denied = _require_site_reports_admin_api()
        if denied:
            return denied
        try:
            from app.routes.admin import _send_smtp_mail, _get_email_auth_settings

            payload = request.get_json(silent=True) or {}
            to_email = str(payload.get('to_email', '')).strip()
            if not to_email:
                return jsonify({'success': False, 'message': '请提供收件邮箱地址'}), 400

            config = _site_report_get_config_fn()
            smtp_settings = _get_email_auth_settings(config)
            if not smtp_settings.get('configured'):
                return jsonify({
                    'success': False,
                    'message': 'SMTP 未配置，请先在系统设置中配置 SMTP。',
                }), 400

            html_body = (
                '<div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;">'
                '<h2 style="color:#123d71;">定时报告推送测试</h2>'
                '<p>如果您收到此邮件，说明报告自动推送邮箱功能已正确配置。</p>'
                '<hr style="border:none;border-top:1px solid #eee;margin:20px 0;">'
                '<p style="color:#999;font-size:12px;">此邮件由定时报告系统测试发送。</p>'
                '</div>'
            )
            _send_smtp_mail(
                smtp_settings,
                to_email=to_email,
                subject='[网站运营报告] 推送测试邮件',
                html_body=html_body,
                text_body='定时报告推送测试：如果您收到此邮件，说明报告自动推送邮箱功能已正确配置。',
            )
            return jsonify({'success': True, 'message': f'测试邮件已发送至 {to_email}'})
        except Exception as exc:
            return jsonify({'success': False, 'message': f'发送失败: {str(exc)}'}), 500

    # 启动定时报告调度线程
    _start_scheduled_report_worker_once(
        app,
        get_config_fn=get_config if callable(get_config) else (lambda: {}),
        update_config_fn=update_config if callable(update_config) else (lambda c: None),
        data_dir=data_dir,
    )



