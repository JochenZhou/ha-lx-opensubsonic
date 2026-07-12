# LX OpenSubsonic

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/JochenZhou/ha-lx-opensubsonic)](https://github.com/JochenZhou/ha-lx-opensubsonic/releases)

在 Home Assistant 中提供 OpenSubsonic 接口，让 **Music Assistant** 搜索、浏览并播放在线音乐。

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

| 配置项 | 建议 |
|---|---|
| 用户名 / 密码 | 自定义即可，后面给 Music Assistant 使用 |
| 默认搜索源 | 常用：`tx`（QQ 音乐） |
| 音源 JS 链接 | 填你的音源脚本地址，用于播放取链 |
| 优先音质 | 如 `flac` / `320k` |
| 在线歌单曲目虚拟专辑 ID | 默认关闭；若歌单内封面全一样，可开启 |

安装后也可在集成 **选项** 中随时修改。

音源 JS 示例：

```text
https://raw.githubusercontent.com/guoyue2010/lxmusic-/refs/heads/main/V260620/推荐/【推荐】长青SVIP音源v1.2.0（全平台支持无损）.js
```

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

可先浏览器访问：

```text
http://<HA地址>:8123/api/lx_opensubsonic
```

确认返回集成信息。

## 使用说明

### 搜索音乐

1. 打开 Music Assistant
2. 选择本 OpenSubsonic 音源
3. 搜索歌手 / 歌名

支持：

- 歌曲
- 专辑
- 歌手
- QQ 音乐在线歌单（显示为 `[歌单] ...`）

### 播放歌单

1. 搜索关键词（如“周杰伦”）
2. 在结果里找以 **`[歌单]`** 开头的项目
3. 点开即可查看曲目并播放

> 说明：Music Assistant 的 OpenSubsonic 搜索不直接显示“播放列表”，所以在线歌单会以专辑形式展示。

### 若歌单封面全是同一张

到集成选项中开启：

**在线歌单曲目使用歌曲级虚拟专辑 ID**

开启后重新进入歌单，再查看曲目封面。

### 若无法播放

检查这几项：

1. 集成中是否填写了可用的 **音源 JS 链接**
2. Music Assistant 的 Base URL / 账号密码是否正确
3. Home Assistant 与 Music Assistant 网络是否互通
4. 浏览器访问 `/api/lx_opensubsonic` 是否正常

## 功能一览

| 功能 | 说明 |
|---|---|
| 在线搜索 | 歌曲 / 专辑 / 歌手 |
| 在线歌单 | 搜索结果中以 `[歌单]` 展示 |
| 播放 | 通过音源 JS 获取播放链接 |
| 封面 | 支持封面显示 |
| 多搜索源 | `tx` / `wy` / `kg` / `kw` / `mg` |
| 音质选择 | `flac` / `320k` / `128k` 等 |

## 常见问题

**Q：需要单独安装 lxserver 吗？**  
A：不需要。集成本身即可提供 OpenSubsonic 接口。

**Q：为什么歌单不是在“播放列表”里？**  
A：因为 Music Assistant 的 OpenSubsonic 搜索只会展示歌曲/专辑/歌手。本集成把在线歌单映射为搜索结果中的专辑。

**Q：可以热切换搜索源吗？**  
A：可以。在集成选项中修改后会自动重载。

## License

MIT
