# LX OpenSubsonic

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/JochenZhou/ha-lx-opensubsonic)](https://github.com/JochenZhou/ha-lx-opensubsonic/releases)

在 Home Assistant 中提供 **OpenSubsonic 兼容接口**，让 **Music Assistant** 通过协议访问用户配置的数据源与播放地址。

> 合规声明：本项目仅提供 Home Assistant 与 OpenSubsonic 协议桥接能力，不提供、不托管、不分发任何音频文件、播放链接、音源脚本或解密密钥。播放地址完全由用户自行配置且有权使用的自定义服务返回。请仅在拥有合法授权的前提下使用相关内容。

> 本项目修改自 [XCQ0607/lxserver](https://github.com/XCQ0607/lxserver)，以 Home Assistant `custom_component` 方式提供桥接能力。

## 效果预览

### Music Assistant 配置

![MA 配置 OpenSubsonic](docs/images/ma-config.png)

### 搜索歌曲

![搜索歌曲](docs/images/ma-search-tracks.png)

> 说明：Music Assistant 当前 OpenSubsonic provider 不会读取歌曲搜索结果里的 track 封面字段，因此歌曲搜索列表可能不显示封面；歌曲详情、播放页、专辑搜索和歌手搜索的封面不受影响。

### 搜索歌手

![搜索歌手](docs/images/ma-search-artists.png)

### 播放页

![播放页](docs/images/ma-playback.png)

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
| 自定义音源 JS 链接 | 可选；用于连接用户自行配置且有权使用的播放地址服务，默认留空 |
| 优先音质 | 如 `flac` / `320k` |

安装后可用实体随时切换：

- **默认搜索源**（下拉）
- **优先音质**（下拉）
- **健康状态**（传感器）
- **测试连接**（按钮）
- **歌单导入相关实体**（文本 / 选择 / 按钮）

重新配置菜单仅用于修改：用户名、密码、自定义音源 JS 链接。

### 3. 配置 Music Assistant

在 Music Assistant 中添加 **OpenSubsonic Media Server Library**，按字段填写（与截图一致）：

| 字段 | 示例 |
|---|---|
| Username | 与集成一致，如 `admin` |
| Password | 与集成一致 |
| Base URL | `http://<你的HA地址>` |
| Port | `8123` |
| Server Path | `/api/lx_opensubsonic` |

说明：

- 实际 REST 入口为：`http://<HA>:8123/api/lx_opensubsonic/rest/...`
- 若你的 MA 版本把路径拆成 `Base URL + Port + Server Path`，请按上表填写
- 若版本只有一个 Base URL 字段，可写：`http://<HA>:8123/api/lx_opensubsonic`

## 支持功能

- 在线搜索：歌曲 / 专辑 / 歌手
- 播放地址跳转（仅使用用户自行配置且有权使用的自定义源）
- 封面显示
- 多搜索源：`tx` / `wy` / `kg` / `kw` / `mg`
- 音质选择
- 健康状态传感器与测试连接按钮
- **手动导入多平台歌单** 到 OpenSubsonic 播放列表（供 MA 播放列表使用）

## 歌单导入（手动）

支持通过实体 UI 手动导入多平台歌单到 OpenSubsonic 播放列表：

- QQ 音乐 `tx`
- 网易云 `wy`
- 酷狗 `kg`
- 酷我 `kw`
- 咪咕 `mg`

步骤：

1. 填写 `歌单链接或ID`
2. 选择 `歌单平台`（可自动识别；纯数字 ID 默认按 QQ）
3. 点击 `导入歌单`
4. 在 Music Assistant 中让歌单进入库（按顺序）：
   1. 先到音乐源「OpenSubsonic Media Server Library」点**重载/立即同步**
   2. 若还没有，再去「浏览 → OpenSubsonic Media Server Library → 播放列表」点开一次
   3. 仍没有再**重启 Music Assistant**

多歌单管理：

- `已导入歌单`：选择当前歌单
- `刷新歌单`：刷新当前选中
- `删除歌单`：删除当前选中

### 明确不支持

- **不支持在线播放列表 / 歌单搜索**
- 不会在搜索结果中映射歌单
- 搜索页不会出现导入歌单

### 已知限制

- Music Assistant 当前 OpenSubsonic provider 不会读取歌曲搜索结果里的 track 封面字段，因此歌曲搜索列表可能不显示封面；歌曲详情、播放页、专辑搜索和歌手搜索的封面不受影响。
- 为保证歌单打开速度，默认不声明 `songLyrics` 扩展；歌词接口只走已缓存歌曲的快速路径，不做搜索兜底。
- 自定义音源 JS 链接默认留空；本项目不提供、不托管、不分发任何音频文件、播放链接、音源脚本或解密密钥，也不保证第三方服务可用性。
- 内存歌曲/封面缓存有数量上限，HA 重启后会重新按搜索或歌单访问重建。

### Music Assistant 注意

- MA「自带播放列表」是本地库缓存
- 文件夹浏览是实时接口，导入后这里一定能看到
- 导入成功通知里也会附带同步顺序提示

## 使用说明

1. 打开 Music Assistant
2. 选择本 OpenSubsonic 音源
3. 搜索歌手或歌名
4. 播放歌曲

若无法播放：

1. 检查自定义音源 JS 链接是否可用，并确认你有权使用其返回的播放地址
2. 点击集成里的 **测试连接** 按钮
3. 确认 MA 的 Base URL / Port / Server Path / 账号密码是否正确

## 验证脚本

发版或部署后可运行最小 OpenSubsonic 冒烟测试：

```bash
python3 scripts/smoke_test.py \
  --base http://<HA>:8123/api/lx_opensubsonic \
  --username admin \
  --password password \
  --query 周杰伦
```

脚本会检查 `ping`、`search3`、`getSong`、`getAlbum`、`getCoverArt`、`getPlaylists`。

## 贡献与致谢

- 修改自 [XCQ0607/lxserver](https://github.com/XCQ0607/lxserver)
- 面向 Music Assistant 的 OpenSubsonic 桥接思路参考了 lxserver 的 Subsonic 兼容实现
- 感谢 Music Assistant / OpenSubsonic 生态

## 📄 开源协议

本项目基于 **Apache License 2.0** 许可证发行，以下协议是对于 Apache License 2.0 的补充，如有冲突，以以下协议为准。

Apache License 2.0 copyright (c) 2026 xcq0607

词语约定：本协议中的“本项目”指 **LX OpenSubsonic（HA 集成 / OpenSubsonic 桥接）** 及其相关代码与文档；“使用者”指签署本协议的使用者；“第三方平台”指用户选择访问的外部音乐/元数据平台；“版权数据”指包括但不限于图像、音频、名字等在内的他人拥有所属版权的数据。

### 一、数据来源

1. **第三方平台元数据**  
   本项目仅按用户选择的平台接口获取并转换元数据，用于 OpenSubsonic 协议展示。本项目不声明这些接口由平台官方授权，也不对数据的合法性、准确性、稳定性负责。

2. **音频与播放地址**  
   本项目不提供、不托管、不分发任何音频文件、播放链接、音源脚本或解密密钥。播放地址完全由使用者自行配置且有权使用的自定义服务返回；本项目无法校验其合法性、准确性或可用性。

3. **其他数据**  
   本项目的本地数据（例如手动导入的歌单列表）来自使用者输入和本地存储，本项目不对这些数据的合法性、准确性负责。

### 二、免责声明

1. **版权数据**  
   使用本项目过程中可能访问或缓存版权数据。对于这些版权数据，本项目不拥有所有权。使用者应仅在拥有合法授权的前提下使用相关内容，并自行遵守所在地法律法规、平台服务条款和版权要求。

2. **责任承担**  
   由于使用本项目产生的包括由于本协议或由于使用或无法使用本项目而引起的任何性质的任何直接、间接、特殊、偶然或结果性损害由使用者负责。

3. **法律法规**  
   本项目完全免费并开源发布，仅用于 Home Assistant 集成、OpenSubsonic 协议兼容和技术研究。禁止在违反当地法律法规、平台服务条款或版权授权的情况下使用本项目。使用者因使用本项目造成的任何违法违规行为由使用者自行承担。

### 三、其他

1. **资源使用**  
   本项目内使用的部分包括但不限于字体、图片等资源来源于互联网。如果出现侵权可联系本项目移除。

2. **非商业性质**  
   本项目仅用于 Home Assistant 集成、协议兼容与技术可行性研究，不接受任何商业（包括但不限于广告等）合作及捐赠。

3. **接受协议**  
   若你使用了本项目，即代表你接受本协议。

完整 Apache License 2.0 文本见仓库根目录 `LICENSE`。
