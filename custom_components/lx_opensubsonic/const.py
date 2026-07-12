"""LX Music → OpenSubsonic bridge for Home Assistant."""

DOMAIN = "lx_opensubsonic"
DEFAULT_USERNAME = "admin"

# Default search platform
CONF_SEARCH_SOURCE = "search_source"
DEFAULT_SEARCH_SOURCE = "tx"

# Third-party music source as JS URL. Key is parsed from script at runtime, never hard-coded.
CONF_MUSIC_SOURCE_JS_URL = "music_source_js_url"
DEFAULT_MUSIC_SOURCE_JS_URL = (
    "https://raw.githubusercontent.com/guoyue2010/lxmusic-/refs/heads/main/"
    "V260620/%E6%8E%A8%E8%8D%90/%E3%80%90%E6%8E%A8%E8%8D%90%E3%80%91"
    "%E9%95%BF%E9%9D%92SVIP%E9%9F%B3%E6%BA%90v1.2.0%EF%BC%88%E5%85%A8%E5%B9%B3%E5%8F%B0"
    "%E6%94%AF%E6%8C%81%E6%97%A0%E6%8D%9F%EF%BC%89.js"
)

CONF_PREFERRED_QUALITY = "preferred_quality"
DEFAULT_PREFERRED_QUALITY = "flac"

SEARCH_SOURCES = ["tx", "wy", "kg", "kw", "mg"]
QUALITY_OPTIONS = ["flac", "320k", "128k", "flac24bit", "hires"]
