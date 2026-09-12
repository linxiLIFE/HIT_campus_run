# 哈工大乐跑

[English README](README.en.md)

这个小工具生成用于 iPhone Core Location/DVT 测试的 GPX 轨迹，当前支持：

设备支持:
iPhone (ios>=18) AND mac
将iPhone通过数据线连接至mac，且iPhone开启开发者模式

- 哈工大一校区体育场（默认）
- 哈工大二校区田径场

路线不是固定模板：不指定 `--seed` 时，每次运行都会使用新的系统随机种子，并随机化起点、跑道横向偏移、逐圈配速和轨迹波形。脚本会把实际种子打印出来，方便保存后复现某一次结果。

## 快速开始

项目只依赖 Python 标准库；只有使用 `--play` 播放到 iPhone 时才需要安装 `pymobiledevice3`。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

生成一校区默认 2.2 km 路线：

```bash
python3 hit_run_simulator.py \
  --campus campus1 \
  --distance 2200 \
  --pace 5:00
```

生成二校区田径场路线：

```bash
python3 hit_run_simulator.py \
  --campus campus2 \
  --distance 2200 \
  --pace 5:00
```

省略 `--output` 时，一校区写入 `routes/hit_campus_2_2km.gpx`，二校区写入 `routes/hit_campus_ii_2_2km.gpx`。`routes/*.gpx` 已加入 `.gitignore`，不会把个人生成文件误提交到公开仓库。

## 路线来源

代码内置的是公开地图轮廓的缓存副本，并按每个校区单独建立局部米制投影：

| 参数 | 路线 | 内置几何来源 |
| --- | --- | --- |
| `campus1` | 一校区体育场 | [OSM relation 4434603](https://www.openstreetmap.org/relation/4434603) / [way 319275785](https://www.openstreetmap.org/way/319275785) |
| `campus2` | 二校区田径场 | [OSM relation 8914003](https://www.openstreetmap.org/relation/8914003) 的内边界 [way 643311728](https://www.openstreetmap.org/way/643311728) |

数据于 2026-09-12 核对并写入脚本。OpenStreetMap 数据按 [ODbL](https://opendatacommons.org/licenses/odbl/) 提供；公开发布时请保留上面的来源和许可说明。也可以对照[哈工大校园地图](https://map.hit.edu.cn/en/)检查校园和场馆现状。

## 随机化与复现

每次生成会从同一个种子派生多个独立随机流，避免距离修正增加一圈时把前面已经生成的变化重新洗掉。随机因素包括：

- 起点在田径场环线上的位置
- 整条路线的横向位置偏移
- 每圈不同的轻微跑道偏移
- 每圈目标配速（仍受 4:30–5:30/km 输入范围约束）
- 轨迹波形、弯道减速和相关 GPS 噪声

不传 `--seed` 时，脚本使用操作系统随机数；输出中会显示类似 `--seed 123456` 的复现命令。要尽量得到完全相同的 GPX（包括时间戳），同时固定种子和起始时间：

```bash
python3 hit_run_simulator.py \
  --campus campus2 \
  --distance 2200 \
  --pace 5:00 \
  --seed 123456 \
  --start 2026-09-12T08:00:00Z \
  --output /tmp/hit-campus2-seed123456.gpx
```

相同种子在不同的 `--distance`、`--pace`、`--sample-rate` 或 `--gps-noise` 下不代表会得到相同 GPX；这些参数也属于路线结果的一部分。

## 主要参数

| 参数 | 说明 |
| --- | --- |
| `--campus campus1|campus2` | 选择一校区或二校区；也接受 `1`、`2`、`一校区`、`二校区` |
| `--distance METERS` | 总距离，默认 `2200` |
| `--pace PACE` | 目标配速，例如 `5:00`、`5.00` 或 `5.0`；允许范围 4:30–5:30/km |
| `--output PATH` | 输出 GPX 路径；省略时按校区选择默认路径 |
| `--seed INTEGER` | 可选固定随机种子；省略时每次自动生成新种子 |
| `--start ISO8601` | 可选起始时间；省略时使用当前 UTC 时间 |
| `--sample-rate HZ` | 采样频率，默认 `1.0` Hz |
| `--gps-noise METERS` | 相关 GPS 噪声标准差，默认 `0.8` m；需要稳定复现坐标时可设为 `0` |
| `--play` | 生成后调用当前 Python 环境中的 `pymobiledevice3` 播放 |
| `--keep-location-simulation` | 播放结束后保留模拟定位；默认会清除 |
| `--clear` | 只清除 iPhone 模拟定位 |

## 播放到已配置的开发设备

播放前需要在 macOS 上准备好 `pymobiledevice3`，并让 iPhone 通过 USB 连接、信任 Mac，满足开发者模式和 DVT 前置条件：

```bash
python3 hit_run_simulator.py \
  --campus campus2 \
  --pace 5:00 \
  --distance 2200 \
  --play
```

脚本使用当前 Python 解释器调用 `python -m pymobiledevice3`，避免 `sudo` 或多个 Python 环境下调用到旧命令。播放结束或按 `Ctrl-C` 后，默认执行模拟定位清除；也可以手动执行：

```bash
python3 hit_run_simulator.py --clear
```

## 检查与测试

```bash
python3 -m py_compile hit_run_simulator.py
python3 -m unittest -v
```

测试会覆盖两校区的目标距离、种子复现、不同种子产生不同轨迹以及校区别名解析。命令行生成完成后还会重新读取 GPX，报告点数、测得距离、时长和平均配速。

## 使用边界

这个项目只生成或播放 Core Location/GPS 轨迹，不会伪造加速度计、陀螺仪、`CMPedometer`、HealthKit 步数或第三方运动 App 的本地记录。请只在你有权测试的设备、自己的 App 或明确授权的测试环境中使用；不能据此承诺任何平台的真实跑步记录、计步结果或反作弊结果。

地图数据是脚本内的静态缓存，田径场、校内通行规则和第三方 App 行为可能变化。实际使用前请自行确认场地和授权范围。


