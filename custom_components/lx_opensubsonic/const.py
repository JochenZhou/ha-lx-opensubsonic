"""LX Music → OpenSubsonic bridge for Home Assistant."""

DOMAIN = "lx_opensubsonic"
DEFAULT_USERNAME = "admin"

CONF_SEARCH_SOURCE = "search_source"
DEFAULT_SEARCH_SOURCE = "tx"

CONF_MUSIC_SOURCE_JS_URL = "music_source_js_url"
DEFAULT_MUSIC_SOURCE_JS_URL = (
    "https://raw.githubusercontent.com/guoyue2010/lxmusic-/refs/heads/main/"
    "V260620/%E6%8E%A8%E8%8D%90/%E3%80%90%E6%8E%A8%E8%8D%90%E3%80%91"
    "%E9%95%BF%E9%9D%92SVIP%E9%9F%B3%E6%BA%90v1.2.0%EF%BC%88%E5%85%A8%E5%B9%B3%E5%8F%B0"
    "%E6%94%AF%E6%8C%81%E6%97%A0%E6%8D%9F%EF%BC%89.js"
)

CONF_PREFERRED_QUALITY = "preferred_quality"
DEFAULT_PREFERRED_QUALITY = "flac"

PLATFORMS = ["sensor", "select", "button"]

SEARCH_SOURCES = ["tx", "wy", "kg", "kw", "mg"]
QUALITY_OPTIONS = ["flac", "320k", "128k", "flac24bit", "hires"]

SEARCH_SOURCE_OPTIONS = [
    {"value": "tx", "label": "QQ音乐 (tx)"},
    {"value": "wy", "label": "网易云音乐 (wy)"},
    {"value": "kg", "label": "酷狗音乐 (kg)"},
    {"value": "kw", "label": "酷我音乐 (kw)"},
    {"value": "mg", "label": "咪咕音乐 (mg)"},
]

QUALITY_SELECT_OPTIONS = [
    {"value": "flac", "label": "无损 FLAC"},
    {"value": "320k", "label": "高品质 320k"},
    {"value": "128k", "label": "标准 128k"},
    {"value": "flac24bit", "label": "Hi-Res FLAC 24bit"},
    {"value": "hires", "label": "Hi-Res"},
]

SEARCH_SOURCE_LABELS = {o["value"]: o["label"] for o in SEARCH_SOURCE_OPTIONS}
QUALITY_LABELS = {o["value"]: o["label"] for o in QUALITY_SELECT_OPTIONS}
