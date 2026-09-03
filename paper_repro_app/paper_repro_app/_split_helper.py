# 数据集 train/val/test 自动划分（供云端 exec 使用）
# 参数：sys.argv[1]=比例 "70,20,10"，sys.argv[2]=已生成的数据集 YAML（相对 repo 根）
# 逻辑：样本收集(images/labels 同构) → 固定种子洗牌 → 按比例软链接到 *_split 目录 → 生成新 YAML → 覆写 env
import json
import os
import random
import shutil
import sys
from pathlib import Path

import yaml as _yaml

_split_spec = (sys.argv[1] if len(sys.argv) > 1 else '').strip()
_cfg_arg = (sys.argv[2] if len(sys.argv) > 2 else '').strip()
if not _split_spec or not _cfg_arg:
    raise SystemExit('[split] 参数缺失（需要 比例 与 YAML 路径）')

_root = Path.cwd()
try:
    _parts = [int(x) for x in _split_spec.replace('：', ':').replace('，', ',').replace(',', ':').split(':')]
except Exception:
    _parts = []
if len(_parts) < 2 or sum(_parts) <= 0:
    raise SystemExit('[split] 划分比例无效：' + _split_spec)
_tr_p, _va_p = _parts[0], _parts[1]
_te_p = _parts[2] if len(_parts) > 2 else 0
if _tr_p < 0 or _va_p < 0 or _te_p < 0:
    raise SystemExit('[split] 划分比例不能为负')

_cfg_path = Path(_cfg_arg)
if not _cfg_path.is_absolute():
    _cfg_path = (_root / _cfg_path).resolve()
if not _cfg_path.exists():
    raise SystemExit('[split] 数据集 YAML 不存在：' + str(_cfg_path))
try:
    _cfg = _yaml.safe_load(_cfg_path.read_text(encoding='utf-8')) or {}
except Exception as _e:
    raise SystemExit('[split] 读取 YAML 失败：' + str(_e))

# 数据集根
_base = Path(str(_cfg.get('path') or '.')).expanduser()
if not _base.is_absolute():
    _base = (_cfg_path.parent / _base).resolve()
_images = _base / 'images'
if not _images.is_dir():
    raise SystemExit('[split] 数据集目录缺少 images/：' + str(_base))


def _collect_pool():
    """收集 (图, 标注) 样本对；图片目录平铺或 train*/val* 子目录均可。"""
    pool = []
    _img_dirs = []
    subs = [p for p in sorted(_images.iterdir()) if p.is_dir()]
    if subs:
        _img_dirs = subs
    else:
        _img_dirs = [_images]
    for _idir in _img_dirs:
        for _img in sorted(_idir.iterdir()):
            if _img.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.bmp', '.webp'):
                continue
            _rel = _img.relative_to(_images)
            _lab_rel = _rel.with_suffix('.txt')
            _lab = _base / 'labels' / _lab_rel
            if not _lab.exists():
                continue
            pool.append((str(_img), str(_lab)))
    return pool


def _detect_nc(labels_root):
    nc = 0
    for t in labels_root.rglob('*.txt'):
        try:
            mx = max(int(ln.split()[0]) for ln in t.read_text(errors='ignore').splitlines() if ln.strip())
            nc = max(nc, mx + 1)
        except Exception:
            pass
    return nc or 1


_pool = _collect_pool()
if not _pool:
    raise SystemExit('[split] 未收集到带标注的样本（images/ 与 labels/ 需同级且一一对应）')
# 已有划分检测（train/val 目录均非空则跳过）
_existing = [_base / 'images' / x for x in ('train', 'val', 'test')]
if all(p.is_dir() and any(p.iterdir()) for p in _existing[:2]):
    print('[split] 数据集已包含 train/val 划分，跳过自动划分。')
    raise SystemExit(0)

random.seed(2026)
random.shuffle(_pool)
n = len(_pool)
n_te = int(n * _te_p / 100.0)
n_va = int((n - n_te) * _va_p / 100.0)
n_tr = n - n_te - n_va
if n_tr <= 0:
    raise SystemExit('[split] 训练样本数不足（总数 %d）' % n)

_split_root = _base.parent / (_base.name + '_split')
for _part in ('train', 'val', 'test'):
    if (_part == 'test' and _te_p <= 0):
        continue
    (_split_root / 'images' / _part).mkdir(parents=True, exist_ok=True)
    (_split_root / 'labels' / _part).mkdir(parents=True, exist_ok=True)

_order = ['train'] * n_tr + ['val'] * n_va + ['test'] * n_te
idx = 0
for (_src_img, _src_lab), _part in zip(_pool, _order):
    _img_dst = _split_root / 'images' / _part / Path(_src_img).name
    _lab_dst = _split_root / 'labels' / _part / Path(_src_lab).name
    try:
        if not _img_dst.exists():
            os.symlink(os.path.abspath(_src_img), str(_img_dst))
        if not _lab_dst.exists():
            os.symlink(os.path.abspath(_src_lab), str(_lab_dst))
    except OSError:
        shutil.copy2(_src_img, _img_dst)
        shutil.copy2(_src_lab, _lab_dst)
    idx += 1

_nc = _detect_nc(_split_root / 'labels')
_names = _cfg.get('names')
if not isinstance(_names, dict):
    _names = {i: 'class_' + str(i) for i in range(_nc)}

_lines = [
    'path: ' + str(_split_root.resolve()),
    'train: images/train',
    'val: images/val',
]
if _te_p > 0:
    _lines.append('test: images/test')
_lines.append('nc: ' + str(_nc))
_lines.append('names: ' + repr(dict(_names)))
_split_yaml = _split_root / 'paper_repro_split.yaml'
_split_yaml.write_text('\n'.join(_lines) + '\n', encoding='utf-8')

# 覆写 env，训练命令将使用新划分
try:
    _rel = str(_split_yaml.relative_to(_root))
except ValueError:
    _rel = str(_split_yaml)
_env = _root / '.paper_repro_dataset.env'
_env.write_text('export PAPER_REPRO_DATA_CONFIG=' + json.dumps(_rel) + '\n', encoding='utf-8')
print('[split] 自动划分完成：train=%d / val=%d / test=%d（总数 %d），配置：%s'
      % (n_tr, n_va, n_te, n, _rel))
