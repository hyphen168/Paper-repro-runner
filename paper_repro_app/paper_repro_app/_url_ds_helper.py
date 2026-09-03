# 数据集 URL 直链处理（供云端 .dep_dataset.py 通过 exec 执行，共享其命名空间）
# 注意：本文件保持顶层可执行代码风格；使用 requested/root/load_candidate 等上游变量。
if requested.startswith(('http://', 'https://')):
    print('数据集直链下载：' + requested)
    data_home = root / 'datasets'
    data_home.mkdir(parents=True, exist_ok=True)
    _free = shutil.disk_usage(data_home).free / (1024 ** 3)
    if _free < 1.5:
        raise SystemExit('磁盘剩余不足 1.5GB，已阻止数据集下载')
    _fname = Path(urllib.request.urlparse(requested).path).name or 'dataset.zip'
    archive = data_home / _fname
    _dl = requested
    for _at in range(3):
        try:
            _req = urllib.request.Request(_dl, headers={'User-Agent': 'paper-repro/1.0'})
            with urllib.request.urlopen(_req, timeout=600) as _resp:
                with open(archive, 'wb') as _fh:
                    shutil.copyfileobj(_resp, _fh)
            break
        except urllib.error.HTTPError as _he:
            if _he.code in (301, 302, 303, 307, 308) and _he.headers.get('Location'):
                _dl = _he.headers['Location']
                continue
            raise SystemExit('数据集下载失败(HTTP %s)：%s' % (_he.code, requested))
        except (TimeoutError, OSError, urllib.error.URLError):
            if _at == 2:
                raise SystemExit('数据集下载失败（网络错误）：' + requested)
            time.sleep(3)
    print('下载完成，正在解压...')
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as _z:
            _z.extractall(data_home)
    elif tarfile.is_tarfile(archive):
        with tarfile.open(archive) as _z:
            _z.extractall(data_home, filter='data')
    else:
        archive.unlink(missing_ok=True)
        raise SystemExit('下载文件不是支持的 ZIP/TAR 包：' + str(archive))
    archive.unlink(missing_ok=True)
    _found = None
    for _p in data_home.rglob('*.yaml'):
        if load_candidate(_p) is not None:
            _found = str(_p)
            break
    if _found is None:
        for _base in sorted(pth for pth in data_home.iterdir() if pth.is_dir()):
            _imgd = _base / 'images'
            if not _imgd.is_dir():
                continue
            _tr = sorted(pth.name for pth in _imgd.iterdir() if pth.is_dir() and 'train' in pth.name.lower())
            _va = sorted(pth.name for pth in _imgd.iterdir() if pth.is_dir() and 'val' in pth.name.lower())
            if not _tr:
                continue
            # 部分官方包（如 coco128）只有 train 目录，val 复用 train
            if not _va:
                _va = _tr
            if not (_base / 'labels').is_dir():
                continue
            _nc = 0
            for _t in (_base / 'labels').rglob('*.txt'):
                try:
                    _mx = max(int(ln.split()[0]) for ln in _t.read_text(errors='ignore').splitlines() if ln.strip())
                    _nc = max(_nc, _mx + 1)
                except Exception:
                    pass
            if _nc <= 0:
                _nc = 1
            _auto = _base / 'paper_repro_auto.yaml'
            # path 用绝对路径：多数框架（yolov5 等）按 cwd 解析相对 path
            _auto.write_text(
                'path: ' + str(_base.resolve()) + '\n'
                'train: images/' + _tr[0] + '\n'
                'val: images/' + _va[0] + '\n'
                'nc: ' + str(_nc) + '\n'
                'names: ' + repr({i: 'class_' + str(i) for i in range(_nc)}) + '\n',
                encoding='utf-8')
            _found = str(_auto)
            print('未发现现成 YAML，已自动生成：' + _found + '（类别 class_0..，可自行改名）')
            break
    if _found is None:
        raise SystemExit('解压后未找到含 images/train+val 与 labels 的目录或现成 YAML。'
                         '（YOLO 格式要求 images/ 与 labels/ 同级）')
    requested = _found
    print('使用数据集配置：' + requested)
