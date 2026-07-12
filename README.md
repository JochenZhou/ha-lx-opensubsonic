# LX OpenSubsonic

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/JochenZhou/ha-lx-opensubsonic)](https://github.com/JochenZhou/ha-lx-opensubsonic/releases)

在 Home Assistant 内提供 **OpenSubsonic 兼容 REST 接口**，把在线音乐能力桥给 **Music Assistant**。  
可不依赖本机 lxserver。

## HACS 安装（推荐）

### 一键添加仓库

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JochenZhou&repository=ha-lx-opensubsonic&category=integration)

1. 确保已安装 [HACS](https://hacs.xyz/)
2. 点击上方徽章，或在 HACS → Integrations → 右上角 ⋮ → **Custom repositories**
3. 仓库地址：

```text
https://github.com/JochenZhou/ha-lx-opensubsonic
```

4. 类别选择 **Integration**
5. 搜索并安装 **LX OpenSubsonic**
6. 重启 Home Assistant
7. 设置 → 设备与服务 → 添加集成 → **LX OpenSubsonic**

### 手动安装

```bash
# 复制到 HA config
cp -r custom_components/lx_opensubsonic /config/custom_components/
```

然后重启 HA 并添加集成。

## 配置项

| 配置 | 说明 |
|---|---|
| 用户名 / 密码 | 给 Music Assistant 连接用 |
| `search_source` | 默认搜索源：`tx` / `wy` / `kg` / `kw` / `mg` |
| `music_source_js_url` | 音源 JS 链接（推荐，运行时解析取链，不内置付费 Key） |
| `preferred_quality` | 优先音质：`flac` / `320k` / `128k` / `flac24bit` / `hires` |
| `playlist_song_virtual_album` | 默认关闭。仅对在线搜索打开的歌单生效：把每首歌 `albumId/parent` 改成歌曲自身 ID，便于 MA 显示每首歌真实封面 |

支持 **Options 热切换** 搜索源 / 音质 / 音源 JS / 歌单虚拟专辑。

### 音源 JS 示例

免费示例（可能混淆，取链能力取决于脚本本身）：

```text
https://raw.githubusercontent.com/guoyue2010/lxmusic-/refs/heads/main/V260620/推荐/【推荐】长青SVIP音源v1.2.0（全平台支持无损）.js
```

付费源请填你自己的私有 JS 链接，**不要公开 Key**。

## Music Assistant 配置

- Provider: **OpenSubsonic Media Server Library**
- Base URL: `http://<HA_IP>:8123/api/lx_opensubsonic`
- Path: `/rest`（若 UI 有 path 字段）
- Username / Password: 集成中配置的账号

也可访问：

```text
http://<HA_IP>:8123/api/lx_opensubsonic
```

查看发现信息。

## 功能

| 能力 | 说明 |
|---|---|
| 搜索 | 歌曲 / 专辑 / 歌手 |
| TX 歌单 | 搜索结果中以 `[歌单] ...` 专辑形式展示 |
| 详情 | `getSong` / `getAlbum` / `getAlbumInfo2` |
| 播放 | `stream`（经音源 JS 取链） |
| 歌词 | 接口兼容（批量加载时快速空返回，避免大歌单卡顿） |
| 封面 | `getCoverArt` 返回图片字节 |

## 说明

1. 常见第三方音源 JS 通常只负责 `musicUrl` 取链，不负责搜索
2. Music Assistant 的 OpenSubsonic 搜索原生不展示 `playlist`，因此 TX 歌单映射为搜索中的专辑
3. 曲目封面优先使用歌曲自身封面，不使用歌单封面兜底

## 接口

```text
/api/lx_opensubsonic/rest/*
```

## License

MIT
