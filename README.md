# 哈工大一校区操场 GPX 模拟脚本

这个小工具生成一条沿哈尔滨工业大学一校区体育场公开地图轮廓的 GPX 轨迹：默认总距离 2.2 km、目标配速 5:00/km、1 Hz 定位点。它会在每圈加入连续的轻微偏道和相关 GPS 误差，同时让配速保持在 4:30–5:30/km 范围内。

轨迹几何来自 OpenStreetMap 的 `relation/4434603` 中的 `way/319275785`，脚本中已内置坐标以便重复生成。公开内圈轮廓约 500 m；脚本把跑线移回卫星图中可见的红色跑道带中部后，生成跑线约 440 m，所以默认 2.2 km 大约是 5 圈。实际手机 GPS、跑道内外沿和地图偏移仍可能让第三方 App 的距离略有差异，不能承诺任何平台的“真实跑步”或反作弊结果。

## 生成 GPX

```bash
python3 hit_run_simulator.py \
  --distance 2200 \
  --pace 5:00 \
  --output routes/hit_campus_2_2km.gpx
```

`--pace 4.30`、`--pace 5.30` 也可以使用；这里的点号格式表示“分.秒”。默认随机种子固定，便于检查和复现；需要另一条轻微误差轨迹时更换 `--seed`。

## 在已配置的开发设备上播放

播放前需要在 macOS 上安装并配置 `pymobiledevice3`，iPhone 通过 USB 连接、信任 Mac，并满足开发者模式/DVT 的前置条件。脚本使用当前 Python 解释器调用模块，避免调用到另一个环境里的旧命令：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python hit_run_simulator.py --play \
  --pace 5:00 \
  --output routes/hit_campus_2_2km.gpx
```

播放结束或按 `Ctrl-C` 后，脚本默认清除模拟定位。若要手动清除：

```bash
python hit_run_simulator.py --clear
```

`--keep-location-simulation` 可以保留播放后的模拟位置，但不建议长期保留，以免之后误以为是真实 GPS。

## 边界

这个脚本只处理 Core Location/GPS 的 GPX 模拟，不会伪造加速度计、陀螺仪、`CMPedometer`、HealthKit 步数或任何运动 App 的本地记录。请只在你有权测试的设备、自己的 App 或明确授权的测试环境中使用。

地图数据来源：哈尔滨工业大学校园地图、哈工大体育部场馆介绍，以及 OpenStreetMap relation 4434603/way 319275785。OpenStreetMap 数据按 ODbL 提供。
