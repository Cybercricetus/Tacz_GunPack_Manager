# TaCZ CurseForge Updater

一个保守的 TaCZ 枪包批量更新器。它只处理 `tacz` 目录第一层的 `.zip` 和 `.jar` 压缩包，通过 CurseForge exact fingerprint 识别项目，并从 CurseForge 官方 API 获取兼容的新版本。

## 设计目标

- 一个枪包失败，不妨碍其他枪包更新。
- fingerprint 和项目查询尽量批量/并行，下载限流并行，文件替换严格串行。
- 新文件通过大小、SHA-1/MD5、CurseForge fingerprint 和 ZIP CRC 校验后才会安装。
- 每个文件独立备份和事务替换；中断后可恢复。
- `--dry-run` 只读取本地文件和联网查询元数据，不下载、不创建 staging、不备份、不修改文件。
- 任何失败都不会自动打开浏览器。

实现遵循 CurseForge 官方 API：`x-api-key` 认证、Minecraft game ID 的 exact
fingerprint 批量匹配、最多 50 条的文件分页，以及官方返回的下载地址和哈希。
接口参考：<https://docs.curseforge.com/rest-api/>

## 环境要求

- Python 3.11 或更新版本
- CurseForge API Key
- Windows、macOS 或 Linux

申请 CurseForge API Key：<https://console.curseforge.com/>

## 安装

### Windows 快捷安装

在 PowerShell 中进入本项目目录：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

也可以手动安装：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
```

macOS/Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
```

## 首次初始化

传入 `tacz` 目录、`.minecraft` 目录或实例根目录：

```powershell
.\.venv\Scripts\tacz-update.exe init `
  "D:\Games\MyInstance\.minecraft\tacz" `
  --minecraft 1.20.1 `
  --loader forge
```

随后程序会隐藏输入 CurseForge API Key，验证后存入操作系统凭据库。API Key 不会写入普通配置文件或日志。

如果已设置临时环境变量，也可以免交互初始化：

```powershell
$env:CURSEFORGE_API_KEY = "你的 Key"
.\.venv\Scripts\tacz-update.exe init "D:\...\.minecraft\tacz" --minecraft 1.20.1
Remove-Item Env:CURSEFORGE_API_KEY
```

## 使用

Dry run：

```powershell
.\.venv\Scripts\tacz-update.exe --dry-run
```

执行更新：

```powershell
.\.venv\Scripts\tacz-update.exe
```

允许 Beta：

```powershell
.\.venv\Scripts\tacz-update.exe --channel beta
```

临时覆盖目录或并发量：

```powershell
.\.venv\Scripts\tacz-update.exe `
  --tacz-dir "D:\OtherInstance\.minecraft\tacz" `
  --jobs 3
```

建议在 Minecraft 完全退出后执行真实更新。

## 输出

```text
SUCCESS [CURRENT] pack-a.zip: already current
SUCCESS [WOULD_UPDATE] pack-b-1.0.zip -> pack-b-1.1.zip: CurseForge file 123 -> 456
FAILURE [UNMATCHED] custom.zip: CurseForge exact fingerprint match not found

SUMMARY success=2 failure=1 update=1 current=1
```

退出码：

| 代码 | 意义 |
| --- | --- |
| `0` | 全部成功 |
| `1` | 至少一个枪包失败；其他枪包可能成功 |
| `2` | 配置、凭据或权限错误 |
| `3` | API/程序级错误，安全中止 |
| `130` | 用户中断 |

## 安全行为

- 不使用 CurseForge fuzzy fingerprint。
- 同一 CurseForge 项目对应多个本地压缩包时，全部标记 `DUPLICATE_PROJECT`，不会猜测该删除哪个。
- 多个项目解析到相同目标文件名时，标记 `TARGET_COLLISION`。
- `downloadUrl` 缺失或第三方下载被禁止时，输出失败，不打开网页。
- 原包备份位于 `.minecraft/.tacz-updater/backups/`。本版本不会自动删除备份。
- staging 和备份与 `tacz` 位于同一文件系统，以便使用原子 rename/replace。
- 当前文件若在扫描后发生变化，会标记 `LOCAL_FILE_CHANGED`，不会覆盖。

## 兼容性边界

CurseForge 可以标注 Minecraft 版本、加载器和发布渠道，但枪包作者未必在元数据中明确声明所需的 TaCZ 具体版本。本工具不会解析更新日志来猜兼容性。因此：

1. 默认只选择同一 CF 项目、相同 Minecraft 版本、兼容加载器的 Release。
2. 多个同时间候选文件会被视作歧义并失败。
3. 更新前保留原包备份。

## 测试

项目测试只使用 Python 标准库：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -v
```

覆盖内容包括：

- CurseForge fingerprint golden vectors 和空白字符归一化
- 只扫描第一层 ZIP/JAR
- 版本和渠道筛选
- 同项目重复包拒绝策略
- 下载哈希及 ZIP 校验
- 替换失败回滚
- 中断 journal 恢复
- dry run 不写磁盘

## 构建单文件 EXE

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build-exe.ps1
```

输出：

```text
dist\tacz-update.exe
```

## 项目结构

```text
tacz_update.py       PyInstaller 入口
build-exe.ps1        Windows 单文件 EXE 构建脚本
install.ps1          Windows 虚拟环境安装脚本
pyproject.toml       项目元数据与依赖
src/tacz_updater/
├── cli.py           命令行入口
├── config.py        路径和配置
├── credentials.py   OS 凭据库
├── fingerprint.py   CurseForge fingerprint
├── scanner.py       本地压缩包扫描
├── curseforge.py    官方 API 和异步下载
├── resolver.py      版本筛选和冲突检测
├── validator.py     下载校验
├── transaction.py   备份、替换和恢复
├── updater.py       更新流程编排
└── output.py        SUCCESS/FAILURE 输出
```

## License

MIT
