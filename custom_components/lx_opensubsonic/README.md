# LX OpenSubsonic

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/JochenZhou/ha-lx-opensubsonic)](https://github.com/JochenZhou/ha-lx-opensubsonic/releases)

在 Home Assistant 中提供 OpenSubsonic 接口，让 **Music Assistant** 搜索并播放在线音乐。

## 快速开始

### 1. 安装集成

#### 方式 A：HACS（推荐）

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JochenZhou&repository=ha-lx-opensubsonic&category=integration)

1. 先安装 [HACS](https://hacs.xyz/)
2. 点击上方按钮，或在 HACS → 集成 → 右上角 ⋮ → **自定义仓库**
3. 仓库地址：

```text
https://github.com/JochenZhou/ha-lx-opensubsonic
```

4. 类别选择 **Integration**
5. 搜索并安装 **LX OpenSubsonic**
6. 重启 Home Assistant
7. 设置 → 设备与服务 → 添加集成 → **LX OpenSubsonic**

#### 方式 B：手动安装

把 `custom_components/lx_opensubsonic` 复制到 Home Assistant 的 `config/custom_components/`，重启后添加集成。

### 2. 配置集成

添加集成时填写：

| 配置项 | 说明 |
|---|---|
| 用户名 / 密码 | 给 Music Assistant 连接使用 |
| 默认搜索源 | 如 `tx`（QQ 音乐） |
| 音源 JS 链接 | 用于解析播放链接 |
| 优先音质 | 如 `flac` / `320k` |

安装后可用实体随时切换：

- **默认搜索源**（下拉）
- **优先音质**（下拉）
- **健康状态**（传感器）
- **测试连接**（按钮）

重新配置菜单仅用于修改：用户名、密码、音源 JS 链接。

### 3. 配置 Music Assistant

在 Music Assistant 中添加：

- **Provider**：OpenSubsonic Media Server Library
- **Base URL**：`http://<你的HA地址>:8123/api/lx_opensubsonic`
- **Path**：`/rest`（有该字段时填写）
- **Username / Password**：与集成中一致

示例：

```text
http://192.168.1.100:8123/api/lx_opensubsonic
```

## 支持功能

- 在线搜索：歌曲 / 专辑 / 歌手
- 播放取链（通过音源 JS）
- 封面显示
- 多搜索源：`tx` / `wy` / `kg` / `kw` / `mg`
- 音质选择
- 健康状态传感器与测试连接按钮

## 不支持功能

- **不支持在线播放列表 / 歌单**
- 不会在搜索结果中映射歌单
- 不会提供可浏览的在线歌单库

Music Assistant 的 OpenSubsonic 播放列表能力依赖服务端 `getPlaylists/getPlaylist`。  
本集成明确不实现该能力，请仅使用歌曲 / 专辑 / 歌手搜索与播放。

## 使用说明

1. 打开 Music Assistant
2. 选择本 OpenSubsonic 音源
3. 搜索歌手或歌名
4. 播放歌曲

若无法播放：

1. 检查音源 JS 链接是否可用
2. 点击集成里的 **测试连接** 按钮
3. 确认 Base URL / 账号密码是否正确

## License

MIT
