"""LX Music → OpenSubsonic bridge for Home Assistant."""

DOMAIN = "lx_opensubsonic"
DEFAULT_USERNAME = "admin"

CONF_SEARCH_SOURCE = "search_source"
DEFAULT_SEARCH_SOURCE = "tx"

CONF_MUSIC_SOURCE_JS_URL = "music_source_js_url"
DEFAULT_MUSIC_SOURCE_JS_URL = ""

CONF_PREFERRED_QUALITY = "preferred_quality"
DEFAULT_PREFERRED_QUALITY = "flac"

PLATFORMS = ["sensor", "select", "button", "text"]

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

# playlist import UI state keys (stored in entry data)
CONF_PLAYLIST_INPUT = "playlist_input"
CONF_PLAYLIST_SOURCE = "playlist_source"
DEFAULT_PLAYLIST_SOURCE = "auto"
PLAYLIST_SOURCE_OPTIONS = [
    {"value": "auto", "label": "自动识别"},
    {"value": "tx", "label": "QQ音乐 (tx)"},
    {"value": "wy", "label": "网易云音乐 (wy)"},
    {"value": "kg", "label": "酷狗音乐 (kg)"},
    {"value": "kw", "label": "酷我音乐 (kw)"},
    {"value": "mg", "label": "咪咕音乐 (mg)"},
]
PLAYLIST_SOURCE_LABELS = {o["value"]: o["label"] for o in PLAYLIST_SOURCE_OPTIONS}
