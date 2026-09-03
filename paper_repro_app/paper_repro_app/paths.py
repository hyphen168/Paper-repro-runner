"""统一路径管理：保证应用目录是纯代码，可整体拷贝/替换/分发。

设计原则（可移植性）：
- 所有可变数据（任务库、日志、产物、报告）一律放在用户家目录 ``~/.paper_repro_app``；
- 应用目录内不写入任何用户数据，拷给朋友时零数据泄漏；
- 升级/替换应用文件夹不会丢失任务历史。
"""
from __future__ import annotations

import shutil
from pathlib import Path

# 用户数据根目录（Windows: C:/Users/<你>/.paper_repro_app）
APP_HOME = Path.home() / ".paper_repro_app"

# 任务库（SQLite）
DB_PATH = APP_HOME / "tasks.db"

# 后台日志（含轮转文件 app.log, app.log.1 ...）
LOG_DIR = APP_HOME / "logs"
LOG_FILE = LOG_DIR / "app.log"

# 任务产物/报告/本地存储默认根目录
DEFAULT_DATA_DIR = Path.home() / "paper_repro_data"

# 旧版（应用目录内）数据位置，用于首次运行自动迁移
_APP_DIR = Path(__file__).resolve().parents[1]
LEGACY_DB = _APP_DIR / "data" / "tasks.db"
LEGACY_LOG_DIR = _APP_DIR / "logs"


def ensure_app_home() -> None:
    """确保用户数据目录存在。"""
    APP_HOME.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def migrate_legacy_data() -> list[str]:
    """把旧版存放在应用目录内的数据迁移到用户家目录。

    幂等且安全：只在目标位置不存在时才复制，绝不覆盖新数据。
    返回本次实际迁移的文件列表（供日志展示）。
    """
    ensure_app_home()
    migrated: list[str] = []

    if LEGACY_DB.exists() and not DB_PATH.exists():
        shutil.copy2(LEGACY_DB, DB_PATH)
        migrated.append(str(DB_PATH))

    if LEGACY_LOG_DIR.exists():
        for old_log in sorted(LEGACY_LOG_DIR.glob("app.log*")):
            target = LOG_DIR / old_log.name
            if not target.exists():
                shutil.copy2(old_log, target)
                migrated.append(str(target))

    return migrated
