# Commandos3-chinese-patch

> 《盟军敢死队3：目标柏林》**Steam 版**自制简体中文补丁与全套工具链。
>
> **为什么做这个**：现有民间汉化补丁基本都要求替换成破解版 exe，
> 用在 Steam 2016 版上会出现**花屏/乱码/闪退**。本项目不碰 exe，
> 直接对 Steam 原版资源文件做等长替换 + 自制中文点阵字体，
> 从根上解决 Steam 版的汉化花屏问题。
>
> **本项目全程由 AI 完成**：格式逆向、工具链开发、801 条游戏文本翻译，
> 均由 AI 独立解决，人工仅负责测试反馈与方向决策（详见 FORMAT_NOTES.md）。
>
> 协议：GPL-3.0（见 LICENSE）。

## 成品下载与安装（普通玩家看这里）

- 成品补丁在仓库 `build\final\`（**Steam 版专用**），拖进游戏目录即可游玩；
- 其中 `DATA.PCK`（约 495MB）超过 GitHub 单文件 100MB 限制，
  **请到 [Releases] 页下载**，与本仓库其余文件配合使用；
- 详细安装/还原步骤见 `build\final\安装说明.txt`。

## 开源说明

- 协议 **GPL-3.0**：衍生项目必须以相同协议开源。
- 按维护者决定，仓库包含：工具代码、技术文档、译文工作文件
  （含游戏英文原文与中文译文）、抽取/自制的字体文件、成品补丁
  （DATA.PCK 除外，走 Release）。
- **不含**：游戏原版 PCK 备份、任何 API 密钥（llm_config.json 已被
  .gitignore 排除）、自制术语字典。
- **免责声明**：本项目与 Pyro Studios / Eidos / Kalypso 等版权方无关，
  不提供游戏本体；使用本项目需要你拥有正版游戏。项目按"现状"提供，
  不作任何担保，风险自担。

## 一、安装 / 还原（Steam 版）

**安装**（`build\final\` + Release 的 DATA.PCK）：
1. `DATA.PCK`、`data3.pck` 拖进游戏根目录覆盖：
   `G:\steam\steamapps\common\Commandos 3 Destination Berlin\`
2. `Data` 文件夹整个拖进游戏根目录，合并 + 全部覆盖；
3. 启动游戏。

**还原原版**：Steam 库右键游戏 → 属性 → 已安装文件 → 验证文件完整性，
然后删除游戏目录 `Data\FONTS\` 下三个字体文件。

## 二、从零复现（新机器上手）

```
:: 0. 准备：Python 3.10+ 与 Pillow（pip install pillow）；
::     游戏路径如非 G:\steam\...，设环境变量 C3EXE 指向你的 Commandos3.exe，
::     仓库位置非默认时设 C3WORK 指向仓库根目录
:: 1. 从你自己的游戏目录备份原版包，再生成工作文件
copy 你的游戏目录\DATA.PCK    backup\DATA.PCK.original
copy 你的游戏目录\data3.pck   backup\data3.pck.original
python tools\make_workfiles.py
python tools\dump_readable.py        :: 可读明文 -> extract_cn\
:: 2. 生成中文 BFT 字体（需 Windows 自带宋体 simsun.ttc）
python -c "import sys,os;sys.path.insert(0,'tools');import fontlib;os.makedirs(r'assets\Data\FONTS',exist_ok=True);fontlib.build_bft_mode(r'assets\Data\FONTS\FONT_UNICODE.BFT','SMALL')"
:: 3. 原版官方小字体 Font_6/Font_8.fnm 由构建器自动从原版包去混淆提取，
::    无需手动准备（见 FORMAT_NOTES.md 第 6 节）
:: 4. AI 翻译（先按下方「AI 翻译配置」建好配置文件）
python tools\translate_llm.py
:: 5. 构建 -> build\final
python tools\build_final.py
```

> 注意：`make_workfiles.py` 会重置 workspace 并**清空所有 zh**，已有
> 译文时不要跑。第 4 步也可人工翻译，工作文件格式见 workspace 内 JSON。

## 三、AI 翻译配置（不入库，本地自建）

创建 `translation\llm_config.json`（已被 .gitignore 排除，不会提交）：

```json
{
  "base_url": "https://api.openai.com/v1",
  "api_key": "你的密钥",
  "model": "gpt-4o-mini",
  "temperature": 0.3,
  "max_batch_chars": 2400,
  "sleep_s": 0.5,
  "max_rounds": 3
}
```

`base_url` 填 OpenAI 兼容地址（到 `/v1` 为止），任何兼容网关均可。

## 四、目录结构

```
Commandos3-chinese-patch\
├── README.md                 本指南
├── FORMAT_NOTES.md           技术全记录（格式规律/踩坑史/成功路径）
├── LICENSE                   GPL-3.0
├── backup\                   原版 PCK 备份（不入库；还原/构建基准用）
├── assets\Data\FONTS\        字体三件套（构建时复制）
├── translation\
│   ├── workspace\<名>.json   译文工作文件（KEY -> 预算/原文/中文）
│   └── llm_config.json       API 配置（不入库，含密钥）
├── extract_cn\               可读明文（浏览/抽查用）
├── build\final\              ★成品输出（DATA.PCK 不入库，走 Release）
└── tools\                    工具链（见下）
```

## 五、日常工作流（改了译文就跑第 2 步）

```
:: 1. AI 翻译（只翻 zh 为空的条目，断点续跑）
python tools\translate_llm.py              :: 全部未译
python tools\translate_llm.py GLOBAL       :: 指定文件
python tools\translate_llm.py --check      :: 只校验不调 API

:: 2. 构建成品 -> build\final
python tools\build_final.py
```

想改某条译文：直接编辑 `translation\workspace\<名>.json` 对应条目的
`zh` 字段（别超 `budget`），跑第 2 步即可。
想重翻某文件：把该 json 里对应 `zh` 清空，跑第 1 步指定该文件。

## 六、字体

- **默认小字号**（实测好看的那版）：汉字 16×13 墨迹/步进 17，
  ASCII 比例步进；已内置于 assets 与成品。
- 想换回大字号（32×26 满格）：
  ```
  python -c "import sys;sys.path.insert(0,'tools');import fontlib;fontlib.build_bft_mode(r'assets\Data\FONTS\FONT_UNICODE.BFT','FULL')"
  python tools\build_final.py
  ```
- 想重新生成小字号：同上把 `'FULL'` 换 `'SMALL'`。
- 字体只影响散装 `Data\FONTS\FONT_UNICODE.BFT`，与 PCK 无关；
  也可单独把生成的文件拖进游戏目录 `Data\FONTS\` 覆盖测试。

## 七、工具链一览（tools\）

| 文件 | 用途 |
|---|---|
| c3pck.py | PCK 容器扫描/等长替换 + 绝对偏移去混淆 |
| strlib.py | STR 编解码/整文解析/GBK 伪单元转换 |
| fontlib.py | BFT 字体生成（SMALL 默认/FULL 可选）与解码校验 |
| make_workfiles.py | 原版包 → 工作文件（重置 workspace 用，会清空 zh，慎跑） |
| dump_readable.py | 工作文件 → extract_cn 可读明文 |
| translate_llm.py | AI 翻译器（OpenAI 兼容 API） |
| build_final.py | 成品构建器（校验+双包+字体+md5+安装说明） |
| disasm.py | exe 反汇编助手（逆向用，平时用不到） |

## 八、成品校验（build_final.py 自动执行）

译文预算/GBK/占位符校验 → 全部用字与字体逐像素闭环 → 双包差异
范围逐字节检查 → 成品回读逐条比对 → md5 清单。
