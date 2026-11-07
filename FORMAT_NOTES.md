# 盟军敢死队3（Steam 2016）自制简体中文补丁 — 技术全记录

> 本文档记录本项目破译的全部格式规律与最终成功路径。
> 所有结论均经实测验证（游戏内渲染成功）。
> 使用方法见 `README.md`。
>
> **本项目全程由 AI 完成**：PCK 容器/STR/字体的格式逆向、全部工具链
> 开发、801 条游戏文本的翻译，均由 AI 独立解决；人工仅提供游戏实测
> 反馈与方向决策。逆向方法论（崩溃转储分析、已知明文攻击、反汇编
> 定位、逐字节往返验证）贯穿全文，可供同类老游戏汉化参考。
>
> 最后更新：2026-10-25（全量汉化 + 小字号字体定稿）

## 〇、最终交付状态

- 801 条游戏文本全部汉化（793 译 + 8 条纯空格装饰条目），双包打入；
- 中文渲染走**小字号** BFT（用户实测定稿）：汉字 16×13 墨迹/步进 17，
  ASCII 比例步进。大字号（32×26 满格）随时可用 fontlib 重新生成；
- 成品 = `build\final\`（DATA.PCK + data3.pck + Data\FONTS\ 三件套），
  md5 见 `build\final\md5.txt`。

## 一、项目结构（Commandos3-chinese-patch 仓库）

```
Commandos3-chinese-patch\（仓库根 = tools 的上级目录，可用 C3WORK 覆盖）
├── README.md                  使用指南（安装/工作流/字体切换）
├── FORMAT_NOTES.md            本文档
├── LICENSE                    GPL-3.0
├── backup\                    原版 PCK 备份（不入库；构建基准/还原用）
│   ├── DATA.PCK.original      md5 155542571faba00c91af8415cf8a4d6e
│   └── data3.pck.original     md5 83f7d509c2f4759f33dee572d00d27f3
├── assets\Data\FONTS\         字体三件套（构建时复制进成品）
│   ├── FONT_UNICODE.BFT       自制全 GBK 字体（小字号版，2,227,816 B）
│   ├── Font_6.fnm             原版官方字体抽取（去混淆）
│   └── Font_8.fnm             原版官方字体抽取（去混淆）
├── translation\
│   ├── workspace\<NAME>.json  译文工作文件（KEY -> 预算/flags/en/zh）
│   └── llm_config.json        API 配置（不入库，含密钥）
├── extract_cn\                人类可读的全量明文（浏览/抽查用）
├── build\final\               ★成品输出（Steam 版专用；DATA.PCK 超
│                              GitHub 100MB 上限不入库，走 Release）
└── tools\
    ├── c3pck.py               pck 容器扫描/等长替换 + 绝对偏移去混淆
    ├── strlib.py              STR 编解码 + 整文解析 + GBK 伪单元
    ├── fontlib.py             BFT 字体生成与校验（SMALL 默认/FULL 可选）
    ├── make_workfiles.py      原版包 -> workspace 工作文件（会清空 zh）
    ├── dump_readable.py       workspace -> extract_cn 可读明文
    ├── translate_llm.py       AI 翻译器（OpenAI 兼容 API）
    ├── build_final.py         成品构建器（工作文件 -> 可装补丁）
    └── disasm.py              exe 反汇编助手（逆向用）
```

## 二、工作流（三条命令）

```
:: 1. AI 翻译（断点续跑，只翻 zh 为空的条目）
python tools\translate_llm.py                 :: 全部
python tools\translate_llm.py GLOBAL TUT1     :: 指定文件
python tools\translate_llm.py --limit 20      :: 试跑
python tools\translate_llm.py --check         :: 本地校验不调API

:: 2. 构建成品（未译条目保持英文，可增量构建试玩）
python tools\build_final.py                   :: -> build\final

:: 3. 安装：build\final 的 DATA.PCK/data3.pck 拖进游戏根目录，
::    Data 文件夹合并覆盖进游戏根目录
```

## 三、成功路径（踩坑史，按最终结论写）

### 1. pck 容器（DATA.PCK / data3.pck 同格式）
- 文件头 0x00 = 根目录记录本身，magic `DATA` 就是根目录名。
- 目录表 = 从 0x00 起连续 48 字节记录，锚点 = 名字字段地址 A：
  [A+0..31 名字 NUL 填充][A+32..35 填充][A+36..39 isdir(1=目录,0=文件,
  0xFF=组终结符)][A+40..43 size（目录=FFFFFFFF）][A+44..47 off
  （文件=数据绝对偏移 0x200 对齐；目录=首子记录地址）]
- 目录子项 = 紧随其后的连续记录直到 isdir=1；根子项从 0x30 开始。
- **data3.pck 覆盖（shadow）DATA.PCK 同名文件**：语言文本两层都有，
  打补丁必须两层都打（END/RED/TM_DEMO 仅在 DATA.PCK）。
- ⚠️ 教训：给 TOC 插记录/改名字会把游戏搞到完全打不开（v7）——
  组终结符 0xFF 记录绝不能动。最终方案完全不改 TOC。

### 2. 去混淆定律（所有包内文件统一，VFS 层生效）
- 每 16 字节块首字节 XOR：`key(P) = ((P>>4)&0xF)<<4 | (P//14)&0xF`，
  P = 块在包内的绝对偏移。低半字节序列 0,1,2,3,4,5,6,8,9,A,B,C,D,E
  （跳 7、F）。exe 实现在 0x92c290。XOR 对合。
- STR 文件等价记法：key(k)=((H0+k)&0xF)<<4 | SEQ[(p0+k)%14]，
  (H0,p0) 由块 0（BOM）反推，**再编码时必须沿用原文件的 (H0,p0)**
  （从明文 BOM 反推会错——BER 实测踩坑）。

### 3. STR 文本
- UTF-16LE + BOM，行式 `KEY<TAB>"value"`，`//注释`；值可跨行（MANUALC3
  的 TX01）、可含字面 `\n` 排版转义。
- **等长原位替换**：译文按 UTF-16 单元数 ≤ 原文，不足尾部补空格；
  blob 长度不变 => TOC/偏移/密钥序列全不动。
- 文本源：19 个文件 801 条 50177 单元（CREDITS 制作名单、TM_DEMO
  试玩残留不翻）。

### 4. 中文渲染（最难啃的部分，最终三定律）
1. **FONT.CFG 语言开关**：DATA.PCK 内 68B（数据@0x3435000），
   `.IDIOMAORIENTAL 0->1` 切到东方语言模式（0=西文FNC组, 2=俄文）。
2. **散装优先**：引擎优先加载游戏根目录 `Data\FONTS\` 散装文件，
   包内字体被无视。=> 字体只需放散装目录，无需动包。
   （v8/v9 长期闪退的真凶 = 散装目录残留的旧版坏字体。）
3. **引擎不做 Unicode→GBK 转换**（v10 截图铁证：`音乐`/`音效` 显示
   同一错字 = 同查表[0x97][0xF3]）：渲染时直接把文本 16 位单元拆成
   [高字节=表行, 低字节=表列] 查 BFT。=> **STR 里的中文必须预编码为
   GBK 码伪 Unicode 单元**（官方亚洲本地化同款做法）。
   - strlib.gbk_units() 干这事；GBK 0xD800-0xDFFF 是 UTF-16 孤代理，
     Python 编解码须 errors='surrogatepass'。

### 5. BFT 字体（CFontKanji）
```
[u16 码数][u16 cellHeight=26][u32 bitmapSize]     头 8B
[码数 × (u16 GBK码 + u32 位图内偏移)]             表项 6B/个
[bitmapSize 字节位图区]
```
- 字形 = **6 字节头（引擎直接跳过）+ 纯行程 RLE**：
  `0x40|n` = n 像素背景，`0x80|n` = n 像素笔画，n=byte&0x3F (1..63)；
  **每行严格 32 像素，行程绝不跨行**；字形高 26 行。
- ⚠️ 不用 literal 字节（0x00-0x3F，语义未吃透）；raw 位图直接当
  RLE 解析会指针跑飞（列计数永不回到 32 → 狂奔至未映射内存 → v8-v10
  闪退 @0x8fc615）。
- 全 GBK 空间 + ASCII 共 24035 码，未定义码共享空白格（查表永不 miss）。
- 字库：SimSun 26px 双色栅格化（fontlib.py）。
- **每字水平步进 = 字形首字节**（0x8727a0 `movzx eax,byte ptr [eax]`）：
  满格版 = 32；查无字形回落 32；空格固定 14（0x8727a3 特判）。
  每行解码固定 32 像素（0x8fc578 `cmp eax,0x20`），行数 = 文件头 cellHeight。
- **半尺寸模式**（fontlib.MODES['SMALL']，**现为默认**）：cellHeight 仍 26
  （不动行循环，零风险），墨迹限左 16 列 × 中间 13 行（y0=6），汉字步进 17、
  ASCII 按墨迹宽度比例步进。字形/字距各缩一半，用户实测定稿。
  生成大字号：`fontlib.build_bft_mode(路径, 'FULL')`；小字号：`'SMALL'`。

### 6. FNM 字体（CFontMono，数字/小 UI 用）
```
[u32 bitmapSize][256B 码表][u32@0x104][u32@0x108=1][u32@0x10c=高][u32@0x110]
[count × 16B 度量(宽,?,步进,?)][count × u32 偏移][8bpp 位图, 0x40=墨]
```
- 语言1 模式加载 Font_6.fnm / Font_8.fnm。**用原版官方文件**（从包内
  按绝对偏移定律抽取去混淆），自制仿品度量不对会导致字大小怪异（v10）。

### 7. 成品校验体系（build_final.py 全自动）
- 译文校验：预算/GBK 可编码/%占位符多重集合一致/禁英文引号制表符；
- BFT 闭环：全部用字查表取字形 == SimSun 真栅格（逐像素）；
- 双包差异必须逐字节落在被替换文件范围内；
- 成品回读：解码后逐条与工作文件比对。

## 四、还原原版
backup\ 两文件改回原名覆盖进游戏目录，删游戏 Data\FONTS\ 三字体文件；
或 Steam「验证文件完整性」。
