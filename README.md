# 几何学

《几何学》是 R. EverStarine 编写的五卷本中文数学教材。第一卷第1—20章正文及附录 A—E、第二卷第1—24章已形成初稿；第一卷前言、后记、前两编导言及其余未写部分保留框架。现有稿件尚未正式审核。

## 五卷目录

| 卷次 | 书名 | TeX 源码 | PDF |
|---|---|---|---|
| 第一卷 | 古典几何与光滑流形 | [Book1.tex](Book1/Book1.tex) | [Book1.pdf](Book1.pdf) |
| 第二卷 | 代数拓扑与微分拓扑 | [Book2.tex](Book2/Book2.tex) | [Book2.pdf](Book2.pdf) |
| 第三卷 | 黎曼几何与几何分析 | [Book3.tex](Book3/Book3.tex) | [Book3.pdf](Book3.pdf) |
| 第四卷 | 复几何与辛几何 | [Book4.tex](Book4/Book4.tex) | [Book4.pdf](Book4.pdf) |
| 第五卷 | 代数几何 | [Book5.tex](Book5/Book5.tex) | [Book5.pdf](Book5.pdf) |

五卷各自独立编号，章号跨编连续，附录从 A 重新开始。章、节的星号表示选读；各卷阅读条件与证明范围见稿件中的相应说明。

## 公开文件

```text
Book1/ … Book5/       各卷 TeX 正文、图表源码及单卷编译入口
Shared/               共用 TeX 样式、数学宏、References.bib 与 geometry.ist
scripts/Build-Book.ps1 共同编译实现
build.ps1             根目录编译入口
Book1.pdf … Book5.pdf  各卷最近一次成功构建的预览
README.md             项目与公开文件说明
.gitignore            发布与缓存排除规则
.gitattributes        文本换行与 PDF 文件属性
```

卷内按 `PartNN/ChapterNN/` 组织编章，附录按 `Appendices/AppendixX/` 组织。书前、书后单篇文件直接放在 `FrontMatter/`、`BackMatter/`，图表源码放在 `Figures/`、`Tables/`。

GitHub 发布教材源码、五卷 PDF、本说明及复编所需的书目库、索引样式、编译脚本和配置。工作记录、写作规范、总纲、研究原件及内部核验材料仅在本地维护。

## 编译

使用已安装的 TeX Live，并确保 `xelatex`、`biber`、`makeindex` 可从终端调用。稿件采用 `ctexbook` 与 XeLaTeX 排版，书目使用 Biber，中文、外文及符号索引由项目脚本处理。

在项目根目录编译单卷，例如第一卷：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -Book 1
```

将 `1` 改为 `2` 至 `5` 选择对应卷；省略 `-Book 1` 编译五卷。Windows 下也可双击各卷目录中的 `build-BookN.bat`。

编译缓存写入 `tmp/build/BookN/`，成功后更新卷内预览和根目录 `BookN.pdf`。书目库、索引样式及编译脚本随源码提供；缓存、日志和卷内重复预览不上传。

## 版权

© 2026 R. EverStarine。保留所有权利。本项目未授予开放许可证；公开访问、下载或克隆不构成改编、再许可或商业使用授权。第三方材料的权利归各自权利人所有。
