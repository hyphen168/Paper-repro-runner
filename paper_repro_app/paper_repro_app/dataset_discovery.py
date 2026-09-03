from __future__ import annotations

import base64
import json
from typing import Any, Dict


_HELPER_PRELUDE = """import os as _os, sys as _sys
from pathlib import Path as _Path
try:
    yaml
except NameError:
    try:
        import yaml as _yaml_lib
        _cfg = _os.environ.get('PAPER_REPRO_HELPER_CONFIG', '')
        _raw = _Path(_cfg).read_text(encoding='utf-8') if _cfg and _Path(_cfg).exists() else ''
        if _raw: yaml = _yaml_lib.safe_load(_raw) or {}
        else: yaml = {}
    except Exception:
        yaml = {}
# 安全路径兜底：仓库下载脚本常见的“重命名/移动”操作在下载不完全时直接裸崩，
# 这里将其降级为“存在才执行”，避免整条流水线因可选数据集的目录整理失败而中断。
def _paper_repro_safe_rename(self, target):
    if self.exists():
        return self.__class__.rename_orig(self, target)
    print(f'[paper-repro] 跳过重命名：源路径不存在 {self} -> {target}')
    return target
_Path.rename_orig = _Path.rename
_Path.rename = _paper_repro_safe_rename
"""


_URL_DL_B64 = "aWYgcmVxdWVzdGVkLnN0YXJ0c3dpdGgoKCdodHRwOi8vJywgJ2h0dHBzOi8vJykpOgogICAgcHJpbnQoJ+aVsOaNrumbhuebtOmTvuS4i+i9ve+8micgKyByZXF1ZXN0ZWQpCiAgICBkYXRhX2hvbWUgPSByb290IC8gJ2RhdGFzZXRzJwogICAgZGF0YV9ob21lLm1rZGlyKHBhcmVudHM9VHJ1ZSwgZXhpc3Rfb2s9VHJ1ZSkKICAgIF9mcmVlID0gc2h1dGlsLmRpc2tfdXNhZ2UoZGF0YV9ob21lKS5mcmVlIC8gKDEwMjQgKiogMykKICAgIGlmIF9mcmVlIDwgMS41OgogICAgICAgIHJhaXNlIFN5c3RlbUV4aXQoJ+ejgeebmOWJqeS9meS4jei2syAxLjVHQu+8jOW3sumYu+atouaVsOaNrumbhuS4i+i9vScpCiAgICBfZm5hbWUgPSBQYXRoKHVybGxpYi5yZXF1ZXN0LnVybHBhcnNlKHJlcXVlc3RlZCkucGF0aCkubmFtZSBvciAnZGF0YXNldC56aXAnCiAgICBhcmNoaXZlID0gZGF0YV9ob21lIC8gX2ZuYW1lCiAgICBfZGwgPSByZXF1ZXN0ZWQKICAgIGZvciBfYXQgaW4gcmFuZ2UoMyk6CiAgICAgICAgdHJ5OgogICAgICAgICAgICBfcmVxID0gdXJsbGliLnJlcXVlc3QuUmVxdWVzdChfZGwsIGhlYWRlcnM9eydVc2VyLUFnZW50JzogJ3BhcGVyLXJlcHJvLzEuMCd9KQogICAgICAgICAgICB3aXRoIHVybGxpYi5yZXF1ZXN0LnVybG9wZW4oX3JlcSwgdGltZW91dD02MDApIGFzIF9yZXNwOgogICAgICAgICAgICAgICAgd2l0aCBvcGVuKGFyY2hpdmUsICd3YicpIGFzIF9maDoKICAgICAgICAgICAgICAgICAgICBzaHV0aWwuY29weWZpbGVvYmooX3Jlc3AsIF9maCkKICAgICAgICAgICAgYnJlYWsKICAgICAgICBleGNlcHQgdXJsbGliLmVycm9yLkhUVFBFcnJvciBhcyBfaGU6CiAgICAgICAgICAgIGlmIF9oZS5jb2RlIGluICgzMDEsIDMwMiwgMzAzLCAzMDcsIDMwOCkgYW5kIF9oZS5oZWFkZXJzLmdldCgnTG9jYXRpb24nKToKICAgICAgICAgICAgICAgIF9kbCA9IF9oZS5oZWFkZXJzWydMb2NhdGlvbiddCiAgICAgICAgICAgICAgICBjb250aW51ZQogICAgICAgICAgICByYWlzZSBTeXN0ZW1FeGl0KCfmlbDmja7pm4bkuIvovb3lpLHotKUoSFRUUCAlcynvvJolcycgJSAoX2hlLmNvZGUsIHJlcXVlc3RlZCkpCiAgICAgICAgZXhjZXB0IChUaW1lb3V0RXJyb3IsIE9TRXJyb3IsIHVybGxpYi5lcnJvci5VUkxFcnJvcik6CiAgICAgICAgICAgIGlmIF9hdCA9PSAyOgogICAgICAgICAgICAgICAgcmFpc2UgU3lzdGVtRXhpdCgn5pWw5o2u6ZuG5LiL6L295aSx6LSl77yI572R57uc6ZSZ6K+v77yJ77yaJyArIHJlcXVlc3RlZCkKICAgICAgICAgICAgdGltZS5zbGVlcCgzKQogICAgcHJpbnQoJ+S4i+i9veWujOaIkO+8jOato+WcqOino+WOiy4uLicpCiAgICBpZiB6aXBmaWxlLmlzX3ppcGZpbGUoYXJjaGl2ZSk6CiAgICAgICAgd2l0aCB6aXBmaWxlLlppcEZpbGUoYXJjaGl2ZSkgYXMgX3o6CiAgICAgICAgICAgIF96LmV4dHJhY3RhbGwoZGF0YV9ob21lKQogICAgZWxpZiB0YXJmaWxlLmlzX3RhcmZpbGUoYXJjaGl2ZSk6CiAgICAgICAgd2l0aCB0YXJmaWxlLm9wZW4oYXJjaGl2ZSkgYXMgX3o6CiAgICAgICAgICAgIF96LmV4dHJhY3RhbGwoZGF0YV9ob21lLCBmaWx0ZXI9J2RhdGEnKQogICAgZWxzZToKICAgICAgICBhcmNoaXZlLnVubGluayhtaXNzaW5nX29rPVRydWUpCiAgICAgICAgcmFpc2UgU3lzdGVtRXhpdCgn5LiL6L295paH5Lu25LiN5piv5pSv5oyB55qEIFpJUC9UQVIg5YyF77yaJyArIHN0cihhcmNoaXZlKSkKICAgIGFyY2hpdmUudW5saW5rKG1pc3Npbmdfb2s9VHJ1ZSkKICAgIF9mb3VuZCA9IE5vbmUKICAgIGZvciBfcCBpbiBkYXRhX2hvbWUucmdsb2IoJyoueWFtbCcpOgogICAgICAgIGlmIGxvYWRfY2FuZGlkYXRlKF9wKSBpcyBub3QgTm9uZToKICAgICAgICAgICAgX2ZvdW5kID0gc3RyKF9wKQogICAgICAgICAgICBicmVhawogICAgaWYgX2ZvdW5kIGlzIE5vbmU6CiAgICAgICAgZm9yIF9iYXNlIGluIHNvcnRlZChwdGggZm9yIHB0aCBpbiBkYXRhX2hvbWUuaXRlcmRpcigpIGlmIHB0aC5pc19kaXIoKSk6CiAgICAgICAgICAgIF9pbWdkID0gX2Jhc2UgLyAnaW1hZ2VzJwogICAgICAgICAgICBpZiBub3QgX2ltZ2QuaXNfZGlyKCk6CiAgICAgICAgICAgICAgICBjb250aW51ZQogICAgICAgICAgICBfdHIgPSBzb3J0ZWQocHRoLm5hbWUgZm9yIHB0aCBpbiBfaW1nZC5pdGVyZGlyKCkgaWYgcHRoLmlzX2RpcigpIGFuZCAndHJhaW4nIGluIHB0aC5uYW1lLmxvd2VyKCkpCiAgICAgICAgICAgIF92YSA9IHNvcnRlZChwdGgubmFtZSBmb3IgcHRoIGluIF9pbWdkLml0ZXJkaXIoKSBpZiBwdGguaXNfZGlyKCkgYW5kICd2YWwnIGluIHB0aC5uYW1lLmxvd2VyKCkpCiAgICAgICAgICAgIGlmIG5vdCBfdHIgb3Igbm90IF92YToKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgIGlmIG5vdCAoX2Jhc2UgLyAnbGFiZWxzJykuaXNfZGlyKCk6CiAgICAgICAgICAgICAgICBjb250aW51ZQogICAgICAgICAgICBfbmMgPSAwCiAgICAgICAgICAgIGZvciBfdCBpbiAoX2Jhc2UgLyAnbGFiZWxzJykucmdsb2IoJyoudHh0Jyk6CiAgICAgICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICAgICAgX214ID0gbWF4KGludChsbi5zcGxpdCgpWzBdKSBmb3IgbG4gaW4gX3QucmVhZF90ZXh0KGVycm9ycz0naWdub3JlJykuc3BsaXRsaW5lcygpIGlmIGxuLnN0cmlwKCkpCiAgICAgICAgICAgICAgICAgICAgX25jID0gbWF4KF9uYywgX214ICsgMSkKICAgICAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgICAgICAgICAgcGFzcwogICAgICAgICAgICBpZiBfbmMgPD0gMDoKICAgICAgICAgICAgICAgIF9uYyA9IDEKICAgICAgICAgICAgX2F1dG8gPSBfYmFzZSAvICdwYXBlcl9yZXByb19hdXRvLnlhbWwnCiAgICAgICAgICAgIF9hdXRvLndyaXRlX3RleHQoCiAgICAgICAgICAgICAgICAncGF0aDogLgonCiAgICAgICAgICAgICAgICAndHJhaW46IGltYWdlcy8nICsgX3RyWzBdICsgJwonCiAgICAgICAgICAgICAgICAndmFsOiBpbWFnZXMvJyArIF92YVswXSArICcKJwogICAgICAgICAgICAgICAgJ25jOiAnICsgc3RyKF9uYykgKyAnCicKICAgICAgICAgICAgICAgICduYW1lczogJyArIHJlcHIoe2k6ICdjbGFzc18nICsgc3RyKGkpIGZvciBpIGluIHJhbmdlKF9uYyl9KSArICcKJywKICAgICAgICAgICAgICAgIGVuY29kaW5nPSd1dGYtOCcpCiAgICAgICAgICAgIF9mb3VuZCA9IHN0cihfYXV0bykKICAgICAgICAgICAgcHJpbnQoJ+acquWPkeeOsOeOsOaIkCBZQU1M77yM5bey6Ieq5Yqo55Sf5oiQ77yaJyArIF9mb3VuZCArICfvvIjnsbvliKsgY2xhc3NfMC4u77yM5Y+v6Ieq6KGM5pS55ZCN77yJJykKICAgICAgICAgICAgYnJlYWsKICAgIGlmIF9mb3VuZCBpcyBOb25lOgogICAgICAgIHJhaXNlIFN5c3RlbUV4aXQoJ+ino+WOi+WQjuacquaJvuWIsOWQqyBpbWFnZXMvdHJhaW4rdmFsIOS4jiBsYWJlbHMg55qE55uu5b2V5oiW546w5oiQIFlBTUzjgILvvIhZT0xPIOagvOW8j+imgeaxgiBpbWFnZXMvIOS4jiBsYWJlbHMvIOWQjOe6p++8iScpCiAgICByZXF1ZXN0ZWQgPSBfZm91bmQKICAgIHByaW50KCfkvb/nlKjmlbDmja7pm4bphY3nva7vvJonICsgcmVxdWVzdGVkKQo="

SPLIT_HELPER_B64 = "IyDmlbDmja7pm4YgdHJhaW4vdmFsL3Rlc3Qg6Ieq5Yqo5YiS5YiG77yI5L6b5LqR56uvIGV4ZWMg5L2/55So77yJCiMg5Y+C5pWw77yac3lzLmFyZ3ZbMV095q+U5L6LICI3MCwyMCwxMCLvvIxzeXMuYXJndlsyXT3lt7LnlJ/miJDnmoTmlbDmja7pm4YgWUFNTO+8iOebuOWvuSByZXBvIOague+8iQojIOmAu+i+ke+8muagt+acrOaUtumbhihpbWFnZXMvbGFiZWxzIOWQjOaehCkg4oaSIOWbuuWumuenjeWtkOa0l+eJjCDihpIg5oyJ5q+U5L6L6L2v6ZO+5o6l5YiwICpfc3BsaXQg55uu5b2VIOKGkiDnlJ/miJDmlrAgWUFNTCDihpIg6KaG5YaZIGVudgppbXBvcnQganNvbgppbXBvcnQgb3MKaW1wb3J0IHJhbmRvbQppbXBvcnQgc2h1dGlsCmltcG9ydCBzeXMKZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCgppbXBvcnQgeWFtbCBhcyBfeWFtbAoKX3NwbGl0X3NwZWMgPSAoc3lzLmFyZ3ZbMV0gaWYgbGVuKHN5cy5hcmd2KSA+IDEgZWxzZSAnJykuc3RyaXAoKQpfY2ZnX2FyZyA9IChzeXMuYXJndlsyXSBpZiBsZW4oc3lzLmFyZ3YpID4gMiBlbHNlICcnKS5zdHJpcCgpCmlmIG5vdCBfc3BsaXRfc3BlYyBvciBub3QgX2NmZ19hcmc6CiAgICByYWlzZSBTeXN0ZW1FeGl0KCdbc3BsaXRdIOWPguaVsOe8uuWkse+8iOmcgOimgSDmr5Tkvosg5LiOIFlBTUwg6Lev5b6E77yJJykKCl9yb290ID0gUGF0aC5jd2QoKQp0cnk6CiAgICBfcGFydHMgPSBbaW50KHgpIGZvciB4IGluIF9zcGxpdF9zcGVjLnJlcGxhY2UoJ++8micsICc6JykucmVwbGFjZSgn77yMJywgJywnKS5yZXBsYWNlKCcsJywgJzonKS5zcGxpdCgnOicpXQpleGNlcHQgRXhjZXB0aW9uOgogICAgX3BhcnRzID0gW10KaWYgbGVuKF9wYXJ0cykgPCAyIG9yIHN1bShfcGFydHMpIDw9IDA6CiAgICByYWlzZSBTeXN0ZW1FeGl0KCdbc3BsaXRdIOWIkuWIhuavlOS+i+aXoOaViO+8micgKyBfc3BsaXRfc3BlYykKX3RyX3AsIF92YV9wID0gX3BhcnRzWzBdLCBfcGFydHNbMV0KX3RlX3AgPSBfcGFydHNbMl0gaWYgbGVuKF9wYXJ0cykgPiAyIGVsc2UgMAppZiBfdHJfcCA8IDAgb3IgX3ZhX3AgPCAwIG9yIF90ZV9wIDwgMDoKICAgIHJhaXNlIFN5c3RlbUV4aXQoJ1tzcGxpdF0g5YiS5YiG5q+U5L6L5LiN6IO95Li66LSfJykKCl9jZmdfcGF0aCA9IFBhdGgoX2NmZ19hcmcpCmlmIG5vdCBfY2ZnX3BhdGguaXNfYWJzb2x1dGUoKToKICAgIF9jZmdfcGF0aCA9IChfcm9vdCAvIF9jZmdfcGF0aCkucmVzb2x2ZSgpCmlmIG5vdCBfY2ZnX3BhdGguZXhpc3RzKCk6CiAgICByYWlzZSBTeXN0ZW1FeGl0KCdbc3BsaXRdIOaVsOaNrumbhiBZQU1MIOS4jeWtmOWcqO+8micgKyBzdHIoX2NmZ19wYXRoKSkKdHJ5OgogICAgX2NmZyA9IF95YW1sLnNhZmVfbG9hZChfY2ZnX3BhdGgucmVhZF90ZXh0KGVuY29kaW5nPSd1dGYtOCcpKSBvciB7fQpleGNlcHQgRXhjZXB0aW9uIGFzIF9lOgogICAgcmFpc2UgU3lzdGVtRXhpdCgnW3NwbGl0XSDor7vlj5YgWUFNTCDlpLHotKXvvJonICsgc3RyKF9lKSkKCiMg5pWw5o2u6ZuG5qC5Cl9iYXNlID0gUGF0aChzdHIoX2NmZy5nZXQoJ3BhdGgnKSBvciAnLicpKS5leHBhbmR1c2VyKCkKaWYgbm90IF9iYXNlLmlzX2Fic29sdXRlKCk6CiAgICBfYmFzZSA9IChfY2ZnX3BhdGgucGFyZW50IC8gX2Jhc2UpLnJlc29sdmUoKQpfaW1hZ2VzID0gX2Jhc2UgLyAnaW1hZ2VzJwppZiBub3QgX2ltYWdlcy5pc19kaXIoKToKICAgIHJhaXNlIFN5c3RlbUV4aXQoJ1tzcGxpdF0g5pWw5o2u6ZuG55uu5b2V57y65bCRIGltYWdlcy/vvJonICsgc3RyKF9iYXNlKSkKCgpkZWYgX2NvbGxlY3RfcG9vbCgpOgogICAgIiIi5pS26ZuGICjlm74sIOagh+azqCkg5qC35pys5a+577yb5Zu+54mH55uu5b2V5bmz6ZO65oiWIHRyYWluKi92YWwqIOWtkOebruW9leWdh+WPr+OAgiIiIgogICAgcG9vbCA9IFtdCiAgICBfaW1nX2RpcnMgPSBbXQogICAgc3VicyA9IFtwIGZvciBwIGluIHNvcnRlZChfaW1hZ2VzLml0ZXJkaXIoKSkgaWYgcC5pc19kaXIoKV0KICAgIGlmIHN1YnM6CiAgICAgICAgX2ltZ19kaXJzID0gc3VicwogICAgZWxzZToKICAgICAgICBfaW1nX2RpcnMgPSBbX2ltYWdlc10KICAgIGZvciBfaWRpciBpbiBfaW1nX2RpcnM6CiAgICAgICAgZm9yIF9pbWcgaW4gc29ydGVkKF9pZGlyLml0ZXJkaXIoKSk6CiAgICAgICAgICAgIGlmIF9pbWcuc3VmZml4Lmxvd2VyKCkgbm90IGluICgnLmpwZycsICcuanBlZycsICcucG5nJywgJy5ibXAnLCAnLndlYnAnKToKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgIF9yZWwgPSBfaW1nLnJlbGF0aXZlX3RvKF9pbWFnZXMpCiAgICAgICAgICAgIF9sYWJfcmVsID0gX3JlbC53aXRoX3N1ZmZpeCgnLnR4dCcpCiAgICAgICAgICAgIF9sYWIgPSBfYmFzZSAvICdsYWJlbHMnIC8gX2xhYl9yZWwKICAgICAgICAgICAgaWYgbm90IF9sYWIuZXhpc3RzKCk6CiAgICAgICAgICAgICAgICBjb250aW51ZQogICAgICAgICAgICBwb29sLmFwcGVuZCgoc3RyKF9pbWcpLCBzdHIoX2xhYikpKQogICAgcmV0dXJuIHBvb2wKCgpkZWYgX2RldGVjdF9uYyhsYWJlbHNfcm9vdCk6CiAgICBuYyA9IDAKICAgIGZvciB0IGluIGxhYmVsc19yb290LnJnbG9iKCcqLnR4dCcpOgogICAgICAgIHRyeToKICAgICAgICAgICAgbXggPSBtYXgoaW50KGxuLnNwbGl0KClbMF0pIGZvciBsbiBpbiB0LnJlYWRfdGV4dChlcnJvcnM9J2lnbm9yZScpLnNwbGl0bGluZXMoKSBpZiBsbi5zdHJpcCgpKQogICAgICAgICAgICBuYyA9IG1heChuYywgbXggKyAxKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgIHBhc3MKICAgIHJldHVybiBuYyBvciAxCgoKX3Bvb2wgPSBfY29sbGVjdF9wb29sKCkKaWYgbm90IF9wb29sOgogICAgcmFpc2UgU3lzdGVtRXhpdCgnW3NwbGl0XSDmnKrmlLbpm4bliLDluKbmoIfms6jnmoTmoLfmnKzvvIhpbWFnZXMvIOS4jiBsYWJlbHMvIOmcgOWQjOe6p+S4lOS4gOS4gOWvueW6lO+8iScpCiMg5bey5pyJ5YiS5YiG5qOA5rWL77yIdHJhaW4vdmFsIOebruW9leWdh+mdnuepuuWImei3s+i/h++8iQpfZXhpc3RpbmcgPSBbX2Jhc2UgLyAnaW1hZ2VzJyAvIHggZm9yIHggaW4gKCd0cmFpbicsICd2YWwnLCAndGVzdCcpXQppZiBhbGwocC5pc19kaXIoKSBhbmQgYW55KHAuaXRlcmRpcigpKSBmb3IgcCBpbiBfZXhpc3RpbmdbOjJdKToKICAgIHByaW50KCdbc3BsaXRdIOaVsOaNrumbhuW3suWMheWQqyB0cmFpbi92YWwg5YiS5YiG77yM6Lez6L+H6Ieq5Yqo5YiS5YiG44CCJykKICAgIHJhaXNlIFN5c3RlbUV4aXQoMCkKCnJhbmRvbS5zZWVkKDIwMjYpCnJhbmRvbS5zaHVmZmxlKF9wb29sKQpuID0gbGVuKF9wb29sKQpuX3RlID0gaW50KG4gKiBfdGVfcCAvIDEwMC4wKQpuX3ZhID0gaW50KChuIC0gbl90ZSkgKiBfdmFfcCAvIDEwMC4wKQpuX3RyID0gbiAtIG5fdGUgLSBuX3ZhCmlmIG5fdHIgPD0gMDoKICAgIHJhaXNlIFN5c3RlbUV4aXQoJ1tzcGxpdF0g6K6t57uD5qC35pys5pWw5LiN6Laz77yI5oC75pWwICVk77yJJyAlIG4pCgpfc3BsaXRfcm9vdCA9IF9iYXNlLnBhcmVudCAvIChfYmFzZS5uYW1lICsgJ19zcGxpdCcpCmZvciBfcGFydCBpbiAoJ3RyYWluJywgJ3ZhbCcsICd0ZXN0Jyk6CiAgICBpZiAoX3BhcnQgPT0gJ3Rlc3QnIGFuZCBfdGVfcCA8PSAwKToKICAgICAgICBjb250aW51ZQogICAgKF9zcGxpdF9yb290IC8gJ2ltYWdlcycgLyBfcGFydCkubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQogICAgKF9zcGxpdF9yb290IC8gJ2xhYmVscycgLyBfcGFydCkubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQoKX29yZGVyID0gWyd0cmFpbiddICogbl90ciArIFsndmFsJ10gKiBuX3ZhICsgWyd0ZXN0J10gKiBuX3RlCmlkeCA9IDAKZm9yIChfc3JjX2ltZywgX3NyY19sYWIpLCBfcGFydCBpbiB6aXAoX3Bvb2wsIF9vcmRlcik6CiAgICBfaW1nX2RzdCA9IF9zcGxpdF9yb290IC8gJ2ltYWdlcycgLyBfcGFydCAvIFBhdGgoX3NyY19pbWcpLm5hbWUKICAgIF9sYWJfZHN0ID0gX3NwbGl0X3Jvb3QgLyAnbGFiZWxzJyAvIF9wYXJ0IC8gUGF0aChfc3JjX2xhYikubmFtZQogICAgdHJ5OgogICAgICAgIGlmIG5vdCBfaW1nX2RzdC5leGlzdHMoKToKICAgICAgICAgICAgb3Muc3ltbGluayhvcy5wYXRoLmFic3BhdGgoX3NyY19pbWcpLCBzdHIoX2ltZ19kc3QpKQogICAgICAgIGlmIG5vdCBfbGFiX2RzdC5leGlzdHMoKToKICAgICAgICAgICAgb3Muc3ltbGluayhvcy5wYXRoLmFic3BhdGgoX3NyY19sYWIpLCBzdHIoX2xhYl9kc3QpKQogICAgZXhjZXB0IE9TRXJyb3I6CiAgICAgICAgc2h1dGlsLmNvcHkyKF9zcmNfaW1nLCBfaW1nX2RzdCkKICAgICAgICBzaHV0aWwuY29weTIoX3NyY19sYWIsIF9sYWJfZHN0KQogICAgaWR4ICs9IDEKCl9uYyA9IF9kZXRlY3RfbmMoX3NwbGl0X3Jvb3QgLyAnbGFiZWxzJykKX25hbWVzID0gX2NmZy5nZXQoJ25hbWVzJykKaWYgbm90IGlzaW5zdGFuY2UoX25hbWVzLCBkaWN0KToKICAgIF9uYW1lcyA9IHtpOiAnY2xhc3NfJyArIHN0cihpKSBmb3IgaSBpbiByYW5nZShfbmMpfQoKX2xpbmVzID0gWwogICAgJ3BhdGg6ICcgKyBzdHIoX3NwbGl0X3Jvb3QucmVzb2x2ZSgpKSwKICAgICd0cmFpbjogaW1hZ2VzL3RyYWluJywKICAgICd2YWw6IGltYWdlcy92YWwnLApdCmlmIF90ZV9wID4gMDoKICAgIF9saW5lcy5hcHBlbmQoJ3Rlc3Q6IGltYWdlcy90ZXN0JykKX2xpbmVzLmFwcGVuZCgnbmM6ICcgKyBzdHIoX25jKSkKX2xpbmVzLmFwcGVuZCgnbmFtZXM6ICcgKyByZXByKGRpY3QoX25hbWVzKSkpCl9zcGxpdF95YW1sID0gX3NwbGl0X3Jvb3QgLyAncGFwZXJfcmVwcm9fc3BsaXQueWFtbCcKX3NwbGl0X3lhbWwud3JpdGVfdGV4dCgnXG4nLmpvaW4oX2xpbmVzKSArICdcbicsIGVuY29kaW5nPSd1dGYtOCcpCgojIOimhuWGmSBlbnbvvIzorq3nu4Plkb3ku6TlsIbkvb/nlKjmlrDliJLliIYKdHJ5OgogICAgX3JlbCA9IHN0cihfc3BsaXRfeWFtbC5yZWxhdGl2ZV90byhfcm9vdCkpCmV4Y2VwdCBWYWx1ZUVycm9yOgogICAgX3JlbCA9IHN0cihfc3BsaXRfeWFtbCkKX2VudiA9IF9yb290IC8gJy5wYXBlcl9yZXByb19kYXRhc2V0LmVudicKX2Vudi53cml0ZV90ZXh0KCdleHBvcnQgUEFQRVJfUkVQUk9fREFUQV9DT05GSUc9JyArIGpzb24uZHVtcHMoX3JlbCkgKyAnXG4nLCBlbmNvZGluZz0ndXRmLTgnKQpwcmludCgnW3NwbGl0XSDoh6rliqjliJLliIblrozmiJDvvJp0cmFpbj0lZCAvIHZhbD0lZCAvIHRlc3Q9JWTvvIjmgLvmlbAgJWTvvInvvIzphY3nva7vvJolcycKICAgICAgJSAobl90ciwgbl92YSwgbl90ZSwgbiwgX3JlbCkpCg=="

class DatasetDiscovery:

    """Build a self-contained remote resolver for repository-declared datasets."""

    result_marker = "PAPER_REPRO_DATASET_JSON="
    env_file_name = ".paper_repro_dataset.env"

    @classmethod
    def build_remote_script(cls) -> str:
        return (
            "import base64, json, os, re, shutil, subprocess, sys, tarfile, time, urllib.request, zipfile\n"
            "from pathlib import Path\n"
            "try:\n"
            "    import yaml\n"
            "except ImportError as exc:\n"
            "    raise SystemExit('数据集解析需要 PyYAML：' + str(exc))\n"
            "root = Path.cwd()\n"
            "requested = sys.argv[1].strip()\n"
            "def load_candidate(path):\n"
            "    try:\n"
            "        value = yaml.safe_load(path.read_text(encoding='utf-8')) or {}\n"
            "    except (OSError, UnicodeDecodeError, yaml.YAMLError): return None\n"
            "    if not isinstance(value, dict) or not value.get('train') or not value.get('val'): return None\n"
            "    return value\n"
            "exec(base64.b64decode('IyDmlbDmja7pm4YgVVJMIOebtOmTvuWkhOeQhu+8iOS+m+S6keerryAuZGVwX2RhdGFzZXQucHkg6YCa6L+HIGV4ZWMg5omn6KGM77yM5YWx5Lqr5YW25ZG95ZCN56m66Ze077yJCiMg5rOo5oSP77ya5pys5paH5Lu25L+d5oyB6aG25bGC5Y+v5omn6KGM5Luj56CB6aOO5qC877yb5L2/55SoIHJlcXVlc3RlZC9yb290L2xvYWRfY2FuZGlkYXRlIOetieS4iua4uOWPmOmHj+OAggppZiByZXF1ZXN0ZWQuc3RhcnRzd2l0aCgoJ2h0dHA6Ly8nLCAnaHR0cHM6Ly8nKSk6CiAgICBwcmludCgn5pWw5o2u6ZuG55u06ZO+5LiL6L2977yaJyArIHJlcXVlc3RlZCkKICAgIGRhdGFfaG9tZSA9IHJvb3QgLyAnZGF0YXNldHMnCiAgICBkYXRhX2hvbWUubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQogICAgX2ZyZWUgPSBzaHV0aWwuZGlza191c2FnZShkYXRhX2hvbWUpLmZyZWUgLyAoMTAyNCAqKiAzKQogICAgaWYgX2ZyZWUgPCAxLjU6CiAgICAgICAgcmFpc2UgU3lzdGVtRXhpdCgn56OB55uY5Ymp5L2Z5LiN6LazIDEuNUdC77yM5bey6Zi75q2i5pWw5o2u6ZuG5LiL6L29JykKICAgIF9mbmFtZSA9IFBhdGgodXJsbGliLnJlcXVlc3QudXJscGFyc2UocmVxdWVzdGVkKS5wYXRoKS5uYW1lIG9yICdkYXRhc2V0LnppcCcKICAgIGFyY2hpdmUgPSBkYXRhX2hvbWUgLyBfZm5hbWUKICAgIF9kbCA9IHJlcXVlc3RlZAogICAgZm9yIF9hdCBpbiByYW5nZSgzKToKICAgICAgICB0cnk6CiAgICAgICAgICAgIF9yZXEgPSB1cmxsaWIucmVxdWVzdC5SZXF1ZXN0KF9kbCwgaGVhZGVycz17J1VzZXItQWdlbnQnOiAncGFwZXItcmVwcm8vMS4wJ30pCiAgICAgICAgICAgIHdpdGggdXJsbGliLnJlcXVlc3QudXJsb3BlbihfcmVxLCB0aW1lb3V0PTYwMCkgYXMgX3Jlc3A6CiAgICAgICAgICAgICAgICB3aXRoIG9wZW4oYXJjaGl2ZSwgJ3diJykgYXMgX2ZoOgogICAgICAgICAgICAgICAgICAgIHNodXRpbC5jb3B5ZmlsZW9iaihfcmVzcCwgX2ZoKQogICAgICAgICAgICBicmVhawogICAgICAgIGV4Y2VwdCB1cmxsaWIuZXJyb3IuSFRUUEVycm9yIGFzIF9oZToKICAgICAgICAgICAgaWYgX2hlLmNvZGUgaW4gKDMwMSwgMzAyLCAzMDMsIDMwNywgMzA4KSBhbmQgX2hlLmhlYWRlcnMuZ2V0KCdMb2NhdGlvbicpOgogICAgICAgICAgICAgICAgX2RsID0gX2hlLmhlYWRlcnNbJ0xvY2F0aW9uJ10KICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgIHJhaXNlIFN5c3RlbUV4aXQoJ+aVsOaNrumbhuS4i+i9veWksei0pShIVFRQICVzKe+8miVzJyAlIChfaGUuY29kZSwgcmVxdWVzdGVkKSkKICAgICAgICBleGNlcHQgKFRpbWVvdXRFcnJvciwgT1NFcnJvciwgdXJsbGliLmVycm9yLlVSTEVycm9yKToKICAgICAgICAgICAgaWYgX2F0ID09IDI6CiAgICAgICAgICAgICAgICByYWlzZSBTeXN0ZW1FeGl0KCfmlbDmja7pm4bkuIvovb3lpLHotKXvvIjnvZHnu5zplJnor6/vvInvvJonICsgcmVxdWVzdGVkKQogICAgICAgICAgICB0aW1lLnNsZWVwKDMpCiAgICBwcmludCgn5LiL6L295a6M5oiQ77yM5q2j5Zyo6Kej5Y6LLi4uJykKICAgIGlmIHppcGZpbGUuaXNfemlwZmlsZShhcmNoaXZlKToKICAgICAgICB3aXRoIHppcGZpbGUuWmlwRmlsZShhcmNoaXZlKSBhcyBfejoKICAgICAgICAgICAgX3ouZXh0cmFjdGFsbChkYXRhX2hvbWUpCiAgICBlbGlmIHRhcmZpbGUuaXNfdGFyZmlsZShhcmNoaXZlKToKICAgICAgICB3aXRoIHRhcmZpbGUub3BlbihhcmNoaXZlKSBhcyBfejoKICAgICAgICAgICAgX3ouZXh0cmFjdGFsbChkYXRhX2hvbWUsIGZpbHRlcj0nZGF0YScpCiAgICBlbHNlOgogICAgICAgIGFyY2hpdmUudW5saW5rKG1pc3Npbmdfb2s9VHJ1ZSkKICAgICAgICByYWlzZSBTeXN0ZW1FeGl0KCfkuIvovb3mlofku7bkuI3mmK/mlK/mjIHnmoQgWklQL1RBUiDljIXvvJonICsgc3RyKGFyY2hpdmUpKQogICAgYXJjaGl2ZS51bmxpbmsobWlzc2luZ19vaz1UcnVlKQogICAgX2ZvdW5kID0gTm9uZQogICAgZm9yIF9wIGluIGRhdGFfaG9tZS5yZ2xvYignKi55YW1sJyk6CiAgICAgICAgaWYgbG9hZF9jYW5kaWRhdGUoX3ApIGlzIG5vdCBOb25lOgogICAgICAgICAgICBfZm91bmQgPSBzdHIoX3ApCiAgICAgICAgICAgIGJyZWFrCiAgICBpZiBfZm91bmQgaXMgTm9uZToKICAgICAgICBmb3IgX2Jhc2UgaW4gc29ydGVkKHB0aCBmb3IgcHRoIGluIGRhdGFfaG9tZS5pdGVyZGlyKCkgaWYgcHRoLmlzX2RpcigpKToKICAgICAgICAgICAgX2ltZ2QgPSBfYmFzZSAvICdpbWFnZXMnCiAgICAgICAgICAgIGlmIG5vdCBfaW1nZC5pc19kaXIoKToKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgIF90ciA9IHNvcnRlZChwdGgubmFtZSBmb3IgcHRoIGluIF9pbWdkLml0ZXJkaXIoKSBpZiBwdGguaXNfZGlyKCkgYW5kICd0cmFpbicgaW4gcHRoLm5hbWUubG93ZXIoKSkKICAgICAgICAgICAgX3ZhID0gc29ydGVkKHB0aC5uYW1lIGZvciBwdGggaW4gX2ltZ2QuaXRlcmRpcigpIGlmIHB0aC5pc19kaXIoKSBhbmQgJ3ZhbCcgaW4gcHRoLm5hbWUubG93ZXIoKSkKICAgICAgICAgICAgaWYgbm90IF90cjoKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgICMg6YOo5YiG5a6Y5pa55YyF77yI5aaCIGNvY28xMjjvvInlj6rmnIkgdHJhaW4g55uu5b2V77yMdmFsIOWkjeeUqCB0cmFpbgogICAgICAgICAgICBpZiBub3QgX3ZhOgogICAgICAgICAgICAgICAgX3ZhID0gX3RyCiAgICAgICAgICAgIGlmIG5vdCAoX2Jhc2UgLyAnbGFiZWxzJykuaXNfZGlyKCk6CiAgICAgICAgICAgICAgICBjb250aW51ZQogICAgICAgICAgICBfbmMgPSAwCiAgICAgICAgICAgIGZvciBfdCBpbiAoX2Jhc2UgLyAnbGFiZWxzJykucmdsb2IoJyoudHh0Jyk6CiAgICAgICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICAgICAgX214ID0gbWF4KGludChsbi5zcGxpdCgpWzBdKSBmb3IgbG4gaW4gX3QucmVhZF90ZXh0KGVycm9ycz0naWdub3JlJykuc3BsaXRsaW5lcygpIGlmIGxuLnN0cmlwKCkpCiAgICAgICAgICAgICAgICAgICAgX25jID0gbWF4KF9uYywgX214ICsgMSkKICAgICAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgICAgICAgICAgcGFzcwogICAgICAgICAgICBpZiBfbmMgPD0gMDoKICAgICAgICAgICAgICAgIF9uYyA9IDEKICAgICAgICAgICAgX2F1dG8gPSBfYmFzZSAvICdwYXBlcl9yZXByb19hdXRvLnlhbWwnCiAgICAgICAgICAgICMgcGF0aCDnlKjnu53lr7not6/lvoTvvJrlpJrmlbDmoYbmnrbvvIh5b2xvdjUg562J77yJ5oyJIGN3ZCDop6PmnpDnm7jlr7kgcGF0aAogICAgICAgICAgICBfYXV0by53cml0ZV90ZXh0KAogICAgICAgICAgICAgICAgJ3BhdGg6ICcgKyBzdHIoX2Jhc2UucmVzb2x2ZSgpKSArICdcbicKICAgICAgICAgICAgICAgICd0cmFpbjogaW1hZ2VzLycgKyBfdHJbMF0gKyAnXG4nCiAgICAgICAgICAgICAgICAndmFsOiBpbWFnZXMvJyArIF92YVswXSArICdcbicKICAgICAgICAgICAgICAgICduYzogJyArIHN0cihfbmMpICsgJ1xuJwogICAgICAgICAgICAgICAgJ25hbWVzOiAnICsgcmVwcih7aTogJ2NsYXNzXycgKyBzdHIoaSkgZm9yIGkgaW4gcmFuZ2UoX25jKX0pICsgJ1xuJywKICAgICAgICAgICAgICAgIGVuY29kaW5nPSd1dGYtOCcpCiAgICAgICAgICAgIF9mb3VuZCA9IHN0cihfYXV0bykKICAgICAgICAgICAgcHJpbnQoJ+acquWPkeeOsOeOsOaIkCBZQU1M77yM5bey6Ieq5Yqo55Sf5oiQ77yaJyArIF9mb3VuZCArICfvvIjnsbvliKsgY2xhc3NfMC4u77yM5Y+v6Ieq6KGM5pS55ZCN77yJJykKICAgICAgICAgICAgYnJlYWsKICAgIGlmIF9mb3VuZCBpcyBOb25lOgogICAgICAgIHJhaXNlIFN5c3RlbUV4aXQoJ+ino+WOi+WQjuacquaJvuWIsOWQqyBpbWFnZXMvdHJhaW4rdmFsIOS4jiBsYWJlbHMg55qE55uu5b2V5oiW546w5oiQIFlBTUzjgIInCiAgICAgICAgICAgICAgICAgICAgICAgICAn77yIWU9MTyDmoLzlvI/opoHmsYIgaW1hZ2VzLyDkuI4gbGFiZWxzLyDlkIznuqfvvIknKQogICAgcmVxdWVzdGVkID0gX2ZvdW5kCiAgICBwcmludCgn5L2/55So5pWw5o2u6ZuG6YWN572u77yaJyArIHJlcXVlc3RlZCkK'))\n"
            "if requested:\n"
            "    config_path = Path(requested).expanduser()\n"
            "    if not config_path.is_absolute(): config_path = root / config_path\n"
            "    config_path = config_path.resolve()\n"
            "    config = load_candidate(config_path)\n"
            "    if config is None: raise SystemExit('指定的数据集 YAML 无效或缺少 train/val：' + str(config_path))\n"
            "else:\n"
            "    # 主题相关性：仓库目录名（如 Yolov5m-NEU-DET）拆词作为身份词，\n"
            "    # 只自动下载与身份词匹配的数据集配置，避免 YOLOv5 全量仓这类多 YAML\n"
            "    # 仓库盲目下载无关大数据集（曾把 20GB+ 的 Argoverse 当成 NEU-DET 下载）。\n"
            "    identity = {t.lower() for t in re.split(r'[^A-Za-z0-9]+', Path.cwd().name) if len(t) > 1}\n"
            "    candidates = []\n"
            "    for path in root.rglob('*'):\n"
            "        if path.suffix.lower() not in {'.yaml', '.yml'} or any(part in {'.git', '.venv', 'venv'} for part in path.parts): continue\n"
            "        config = load_candidate(path)\n"
            "        if config is not None:\n"
            "            blob = (path.stem + ' ' + str(config.get('path', '')) + ' ' + str(config.get('names', ''))).lower()\n"
            "            hits = sum(1 for token in identity if token in blob)\n"
            "            candidates.append((hits, 0 if config.get('download') else 1, len(path.parts), str(path).lower(), path, config))\n"
            "    if not candidates:\n"
            "        readmes = list(root.glob('README*'))\n"
            "        links = []\n"
            "        for readme in readmes:\n"
            "            links.extend(re.findall(r'https?://[^\\s)\\]\"<>]+', readme.read_text(encoding='utf-8', errors='ignore')))\n"
            "        dataset_links = [link for link in links if re.search(r'(dataset|data|\\.zip|\\.tar)', link, re.I)]\n"
            "        hint = ('；仓库 README 中发现候选链接：' + ', '.join(dataset_links[:3])) if dataset_links else ''\n"
            "        raise SystemExit('未发现包含 train/val 的数据集 YAML，无法安全自动配置数据集' + hint)\n"
            "    # 选分：相关性命中数 > 是否声明 download > 路径层级浅 > 字母序\n"
            "    _, _, _, _, config_path, config = sorted(candidates, key=lambda item: (item[0], item[1], item[2], item[3]))[0]\n"
            "    if identity and all(item[0] == 0 for item in candidates) and len(candidates) > 1:\n"
            "        listed = ', '.join(sorted(str(item[4].relative_to(root)) for item in candidates[:8]))\n"
            "        raise SystemExit('仓库中存在多个数据集配置且与项目主题不匹配（候选：' + listed + '）。为免误下无关大文件，请在任务表单填写数据 YAML 路径，或改用实际运行模式并填写数据下载命令。')\n"
            "base = Path(str(config.get('path') or '.')).expanduser()\n"
            "if not base.is_absolute(): base = (config_path.parent / base).resolve()\n"
            "splits = []\n"
            "for key in ('train', 'val'):\n"
            "    value = config[key]\n"
            "    if isinstance(value, str): splits.append(base / value)\n"
            "    elif isinstance(value, list): splits.extend(base / item for item in value if isinstance(item, str))\n"
            "complete = bool(splits) and all(path.exists() for path in splits)\n"
            "download = config.get('download')\n"
            "if not complete:\n"
            "    if not isinstance(download, str) or not download.strip():\n"
            "        raise SystemExit('已识别数据集 YAML，但数据集缺失且仓库未声明官方下载指令：' + str(config_path))\n"
            "    print('数据集缺失，执行仓库 YAML 声明的官方下载来源。')\n"
            "    free_gb = 0.0\n"
            "    base.parent.mkdir(parents=True, exist_ok=True)\n"
            "    free_gb = shutil.disk_usage(base.parent).free / (1024 ** 3)\n"
            "    print(f'磁盘剩余空间: {free_gb:.1f} GB')\n"
            "    if free_gb < 1.5:\n"
            "        raise SystemExit(f'磁盘剩余空间不足 1.5GB（当前 {free_gb:.1f}GB），已阻止下载以防占满磁盘，请清理云端空间后重试。')\n"
            "    if download.startswith(('http://', 'https://')):\n"
            "        archive = base.parent / Path(download.split('?', 1)[0]).name\n"
            "        base.parent.mkdir(parents=True, exist_ok=True)\n"
            "        try:\n"
            "            with urllib.request.urlopen(urllib.request.Request(download, method='HEAD'), timeout=30) as resp:\n"
            "                total = int(resp.headers.get('Content-Length') or 0)\n"
            "                if total > 0 and total / (1024 ** 3) > free_gb * 0.8:\n"
            "                    raise SystemExit(f'数据集包大小 {total / (1024 ** 3):.1f}GB 超过磁盘剩余空间 80%（{free_gb:.1f}GB），已阻止下载。')\n"
            "        except SystemExit:\n"
            "            raise\n"
            "        except Exception:\n"
            "            pass  # 服务器不支持 HEAD 时直接下载\n"
            "        # urllib 在 Python 3.10 不自动跟随 308，且网络波动需要重试，故用带重定向跟随的下载函数\n"
            "        _dl_url = download\n"
            "        for _attempt in range(3):\n"
            "            try:\n"
            "                _req = urllib.request.Request(_dl_url, headers={'User-Agent': 'paper-repro/1.0'})\n"
            "                with urllib.request.urlopen(_req, timeout=600) as _resp:\n"
            "                    with open(archive, 'wb') as _fh:\n"
            "                        shutil.copyfileobj(_resp, _fh)\n"
            "                break\n"
            "            except urllib.error.HTTPError as _he:\n"
            "                if _he.code in (301, 302, 303, 307, 308) and _he.headers.get('Location'):\n"
            "                    _dl_url = _he.headers['Location']\n"
            "                    continue\n"
            "                raise\n"
            "            except (TimeoutError, OSError, urllib.error.URLError):\n"
            "                if _attempt == 2:\n"
            "                    raise\n"
            "                time.sleep(3)\n"
            "        if zipfile.is_zipfile(archive):\n"
            "            with zipfile.ZipFile(archive) as bundle: bundle.extractall(base.parent)\n"
            "        elif tarfile.is_tarfile(archive):\n"
            "            with tarfile.open(archive) as bundle: bundle.extractall(base.parent, filter='data')\n"
            "        else: raise SystemExit('数据集下载地址不是支持的 ZIP/TAR 包：' + str(archive))\n"
            "        archive.unlink(missing_ok=True)\n"
            "    else:\n"
            "        is_python_code = any(download.lstrip().startswith(kw) for kw in ('import ', 'from ', '#', '\\nimport', '\\nfrom')) or '\\nimport ' in download or '\\nfrom ' in download\n"
            "        if is_python_code:\n"
            "            temp_py = root / '.paper_repro_download_helper.py'\n"
            "            # 仓库脚本常假设运行在已加载 YAML 字典的上下文中（如 yaml['path']），\n"
            "            # 独立执行会 NameError；注入兜底：未定义 yaml 时从声明下载指令的配置加载为字典\n"
            "            prelude = " + repr(_HELPER_PRELUDE) + "\n"
            "            temp_py.write_text(prelude + download, encoding='utf-8')\n"
            "            py_exec = sys.executable if sys.executable else 'python'\n"
            "            try:\n"
            "                helper_env = dict(os.environ)\n"
            "                helper_env['PAPER_REPRO_HELPER_CONFIG'] = str(config_path)\n"
            "                result = subprocess.run([py_exec, str(temp_py)], cwd=root, capture_output=True, text=True, check=False, env=helper_env)\n"
            "            finally:\n"
            "                temp_py.unlink(missing_ok=True)\n"
            "        else:\n"
            "            result = subprocess.run(download, shell=True, cwd=root, capture_output=True, text=True, check=False)\n"
            "        stderr_msg = ''\n"
            "        if hasattr(result, 'stderr') and result.stderr:\n"
            "            stderr_msg = result.stderr.strip()\n"
            "        if result.returncode:\n"
            "            hint = ('\\n--- stderr ---\\n' + stderr_msg) if stderr_msg else ''\n"
            "            raise SystemExit(f'仓库数据集下载脚本失败（退出码 {result.returncode}）{hint}')\n"
            "    if not all(path.exists() for path in splits):\n"
            "        raise SystemExit('下载后未找到 YAML 声明的 train/val 路径：' + ', '.join(str(path) for path in splits))\n"
            "relative_config = str(config_path.relative_to(root)) if config_path.is_relative_to(root) else str(config_path)\n"
            "env_path = root / '.paper_repro_dataset.env'\n"
            "env_path.write_text('export PAPER_REPRO_DATA_CONFIG=' + json.dumps(relative_config) + '\\n', encoding='utf-8')\n"
            "payload = {'config_path': relative_config, 'dataset_root': str(base), 'downloaded': not complete, 'splits': [str(path) for path in splits]}\n"
            "print('PAPER_REPRO_DATASET_JSON=' + base64.b64encode(json.dumps(payload).encode('utf-8')).decode('ascii'))"
        )

    @classmethod
    def build_remote_command(cls, python_bin: str, data_config: str) -> str:
        encoded = base64.b64encode(cls.build_remote_script().encode("utf-8")).decode("ascii")
        # 落盘执行：先写 .dep_dataset.py 再执行脚本文件，与 dependencies 步骤的
        # .dep_scan.py 模式一致，彻底规避 bash 内联解析截断风险
        return (
            f"{python_bin} -c \"from pathlib import Path; import base64; "
            f"Path('.dep_dataset.py').write_text(base64.b64decode('{encoded}').decode('utf-8'), encoding='utf-8')\""
            f" && {python_bin} .dep_dataset.py {data_config!r}"
        )

    @classmethod
    def extract_payload(cls, log_text: str) -> Dict[str, Any]:
        for line in reversed(log_text.splitlines()):
            if not line.startswith(cls.result_marker):
                continue
            try:
                return json.loads(base64.b64decode(line[len(cls.result_marker):]).decode("utf-8"))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                return {}
        return {}
