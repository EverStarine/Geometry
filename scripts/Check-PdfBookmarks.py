#!/usr/bin/env python3
"""Check finished geometry PDFs against the original outline without rendering.

Requires pypdf.  Only the cover page is text-extracted; PyMuPDF is used as a
fallback for embedded Chinese fonts without a ToUnicode map.  The remaining
checks inspect PDF outline objects and their destinations.  The companion
outline parser supplies the formal scope, excluding introductory summaries.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
import runpy
import sys
import unicodedata

try:
    from pypdf import PdfReader
except ImportError:
    raise SystemExit("需要 pypdf；请使用已安装 pypdf 的 Python 环境运行。")


CHINESE_DIGITS = "零一二三四五六七八九"
CHINESE_NUMBER = r"[零〇一二三四五六七八九十百0-9]+"


@dataclass
class Bookmark:
    title: str
    level: int
    parent: int | None
    destination: object


@dataclass
class Expected:
    key: tuple
    title: str
    level: int
    parent_key: tuple | None


def normalize(text: str) -> str:
    # Preserve symbols, stars and punctuation; PDF spacing is not semantic.
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", text))


def chinese(number: int) -> str:
    if number < 10:
        return CHINESE_DIGITS[number]
    if number < 100:
        tens, ones = divmod(number, 10)
        return (CHINESE_DIGITS[tens] if tens > 1 else "") + "十" + (CHINESE_DIGITS[ones] if ones else "")
    raise ValueError(f"当前纲要不应出现超过两位数的章号：{number}")


def integer(text: str) -> int:
    if text.isascii() and text.isdigit():
        return int(text)
    text = text.replace("〇", "零")
    if "百" in text:
        raise ValueError(f"超出当前纲要范围的中文编号：{text}")
    if "十" in text:
        left, right = text.split("十", 1)
        return (CHINESE_DIGITS.index(left) if left else 1) * 10 + (CHINESE_DIGITS.index(right) if right else 0)
    return CHINESE_DIGITS.index(text)


def structural_key(title: str) -> tuple | None:
    value = normalize(title)
    if value == "附录":
        return ("appendices",)
    if match := re.match(rf"^第({CHINESE_NUMBER})编", value):
        return ("part", integer(match[1]))
    if match := re.match(rf"^第({CHINESE_NUMBER})章", value):
        return ("chapter", integer(match[1]))
    if match := re.match(r"^附录([A-Z])", value):
        return ("appendix", match[1])
    if match := re.match(r"^(\d+|[A-Z])\.(\d+)\.(\d+)", value):
        chapter = int(match[1]) if match[1].isdigit() else match[1]
        return ("subsection", chapter, int(match[2]), int(match[3]))
    if match := re.match(r"^(\d+|[A-Z])\.(\d+)", value):
        chapter = int(match[1]) if match[1].isdigit() else match[1]
        return ("section", chapter, int(match[2]))
    return None


def expected_entries(nodes: list, planned_headings, pdf_inline_title) -> list[Expected]:
    selected = [node for node in nodes if node.kind != "book"]
    key_by_path = {}
    titles = {}
    for node in selected:
        star = "*" if node.optional else ""
        if node.kind == "part":
            key = ("part", int(node.number))
            title = f"第{chinese(int(node.number))}编 {node.title}"
        elif node.kind == "chapter":
            key = ("chapter", int(node.number))
            title = f"第{chinese(int(node.number))}章{star} {node.title}"
        elif node.kind == "section":
            match = re.match(r"^### (\d+)\.(\d+)", node.heading)
            if match is None:
                raise ValueError(f"无法读取原纲要节号：{node.heading}")
            chapter, section = int(match[1]), int(match[2])
            key = ("section", chapter, section)
            title = f"{chapter}.{section}{star} {node.title}"
        elif node.kind == "appendices":
            key, title = ("appendices",), "附录"
        elif node.kind == "appendix":
            key = ("appendix", str(node.number))
            title = f"附录 {node.number} {node.title}"
        else:
            raise ValueError(f"无法识别的纲要节点：{node.kind}")
        key_by_path[node.path] = key
        titles[node.path] = title
    levels = {"part": 0, "chapter": 1, "section": 2, "appendices": 0, "appendix": 1}
    result: list[Expected] = []
    for node in selected:
        node_key = key_by_path[node.path]
        result.append(Expected(node_key, titles[node.path], levels[node.kind],
                               key_by_path.get(node.parent)))
        if node.kind == "section":
            _, chapter, section = node_key
            for subsection, (kind, title) in enumerate(planned_headings(node), 1):
                if kind != "subsection":
                    raise ValueError(f"正文节含有非小节层级：{node.heading}，{kind}。")
                key = ("subsection", chapter, section, subsection)
                numbered_title = f"{chapter}.{section}.{subsection} {pdf_inline_title(title)}"
                result.append(Expected(key, numbered_title, 3, node_key))
        elif node.kind == "appendix":
            chapter = str(node.number)
            section = subsection = 0
            for kind, title in planned_headings(node):
                if kind == "section":
                    section += 1
                    subsection = 0
                    key = ("section", chapter, section)
                    numbered_title = f"{chapter}.{section} {pdf_inline_title(title)}"
                    result.append(Expected(key, numbered_title, 2, node_key))
                elif kind == "subsection":
                    if not section:
                        raise ValueError(f"附录小节没有所属节：{node.heading}，{title}。")
                    subsection += 1
                    key = ("subsection", chapter, section, subsection)
                    numbered_title = f"{chapter}.{section}.{subsection} {pdf_inline_title(title)}"
                    result.append(Expected(key, numbered_title, 3,
                                           ("section", chapter, section)))
                else:
                    raise ValueError(f"附录含有无法识别的标题层级：{node.heading}，{kind}。")
    return result


def flatten_outline(items: list, errors: list[str]) -> list[Bookmark]:
    flattened: list[Bookmark] = []

    def visit(values: list, level: int, parent: int | None) -> None:
        previous: int | None = None
        for value in values:
            if isinstance(value, list):
                if previous is None:
                    errors.append("书签子树没有所属父节点。")
                visit(value, level + 1, previous)
            else:
                title = getattr(value, "title", None)
                if title is None:
                    errors.append("书签缺少标题。")
                    title = ""
                previous = len(flattened)
                flattened.append(Bookmark(str(title), level, parent, value))

    visit(items, 0, None)
    return flattened


def read_finished_pdf(path: Path):
    if not path.is_file():
        raise ValueError(f"成品 PDF 不存在：{path.name}；请等本卷编译完成后再检查。")
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError(f"{path.name} 正在更新；请等编译完成后再检查。")
    if not data.startswith(b"%PDF-") or not data.rstrip().endswith(b"%%EOF"):
        raise ValueError(f"{path.name} 不是完整 PDF；请等编译完成后再检查。")
    return PdfReader(BytesIO(data), strict=True), data


def cover_status(reader, data: bytes, expected_status: str) -> tuple[bool, str]:
    def marked(text: str) -> bool:
        value = normalize(text)
        return normalize(expected_status) in value

    try:
        if marked(reader.pages[0].extract_text() or ""):
            return True, "pypdf"
    except Exception:
        # pypdf cannot recover some embedded CID fonts without ToUnicode;
        # PyMuPDF can use the embedded font cmap.  This performs no rendering.
        pass
    try:
        import fitz
    except ImportError:
        return False, "pypdf 未恢复封面中文；可安装 PyMuPDF 进行字体映射回退"
    with fitz.open(stream=data, filetype="pdf") as document:
        return marked(document[0].get_text()), "PyMuPDF"


def check_book(root: Path, book: int, nodes: list, planned_headings,
               pdf_inline_title) -> tuple[list[str], str]:
    errors: list[str] = []
    reader, data = read_finished_pdf(root / f"Book{book}.pdf")
    if reader.is_encrypted:
        raise ValueError("成品 PDF 被加密，无法核验。")
    page_count = len(reader.pages)
    if page_count == 0:
        raise ValueError("成品 PDF 没有页面。")
    entries = flatten_outline(reader.outline, errors)
    if not entries:
        errors.append("PDF 没有书签。")
    wanted = expected_entries(nodes, planned_headings, pdf_inline_title)
    expected_by_key = {entry.key: entry for entry in wanted}
    actual_by_key: dict[tuple, list[int]] = defaultdict(list)
    actual_order = []
    actual_counts = Counter()

    for index, entry in enumerate(entries):
        if entry.level > 3:
            errors.append(f"出现小节以下的书签层级 {entry.level}：{entry.title!r}。")
        try:
            page = reader.get_destination_page_number(entry.destination)
            if not isinstance(page, int) or page < 0 or page >= page_count:
                errors.append(f"书签目的页无效：{entry.title!r}，page={page!r}。")
        except Exception as exc:
            errors.append(f"书签目的页无法解析：{entry.title!r}（{exc}）。")
        try:
            key = structural_key(entry.title)
        except ValueError as exc:
            errors.append(f"编号无法解析：{entry.title!r}（{exc}）。")
            continue
        if key is not None:
            actual_by_key[key].append(index)
            actual_order.append(key)
            actual_counts[key[0]] += 1
            if key not in expected_by_key:
                errors.append(f"纲要之外的编号书签：{entry.title!r}。")

    expected_counts = Counter(entry.key[0] for entry in wanted)
    for kind, chinese_name in (("part", "编"), ("chapter", "章"), ("section", "节"),
                               ("subsection", "小节"),
                               ("appendix", "附录章"), ("appendices", "附录入口")):
        if actual_counts[kind] != expected_counts[kind]:
            errors.append(f"{chinese_name}书签数量 {actual_counts[kind]}，纲要要求 {expected_counts[kind]}。")
    if actual_order != [entry.key for entry in wanted]:
        errors.append("编、章、节、小节、附录的书签编号或先后次序与原纲要不符。")

    for expected in wanted:
        matches = actual_by_key.get(expected.key, [])
        if not matches:
            errors.append(f"缺少纲要书签：{expected.title!r}。")
            continue
        if len(matches) != 1:
            errors.append(f"编号书签重复：{expected.title!r}，共 {len(matches)} 条。")
            continue
        index = matches[0]
        actual = entries[index]
        if normalize(actual.title) != normalize(expected.title):
            errors.append(f"编号、选读星号或标题不符：实际 {actual.title!r}；应为 {expected.title!r}。")
        if actual.level != expected.level:
            errors.append(f"书签层级不符：{actual.title!r} 为 {actual.level}，应为 {expected.level}。")
        if expected.parent_key is None:
            if actual.parent is not None:
                errors.append(f"顶层入口被嵌套到其他书签之下：{actual.title!r}。")
        else:
            parents = actual_by_key.get(expected.parent_key, [])
            if len(parents) == 1 and actual.parent != parents[0]:
                errors.append(f"书签所属编、章或节不符：{actual.title!r}。")

    main_source = (root / f"Book{book}" / f"Book{book}.tex").read_text(encoding="utf-8-sig")
    shared_source = (root / "Shared" / "Preamble.tex").read_text(encoding="utf-8-sig")
    status_pattern = r"\\(?:newcommand|providecommand)\{\\BookStatus\}\{([^{}]+)\}"
    status_match = re.search(status_pattern, main_source) or re.search(status_pattern, shared_source)
    if status_match is None:
        raise ValueError("找不到卷元数据或共享默认的 BookStatus 稿件状态。")
    expected_status = status_match[1]
    cover_ok, cover_method = cover_status(reader, data, expected_status)
    if not cover_ok:
        errors.append(f"封面未提取到稿件状态“{expected_status}”（{cover_method}）。")
    stats = (f"Book{book}: {page_count} 页，{actual_counts['part']} 编，"
             f"{actual_counts['chapter']} 章，{actual_counts['section']} 节，"
             f"{actual_counts['subsection']} 小节，"
             f"{actual_counts['appendix']} 附录，{len(entries)} 条书签；封面文本：{cover_method}。")
    return errors, stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从原纲要核验已编译 PDF 的书签、目的页与封面稿件状态；无需渲染。",
        epilog="依赖 Python 3.10+、pypdf；可选 PyMuPDF 用于 pypdf 无法解码的嵌入中文字体。")
    parser.add_argument("-Book", "--book", "-b", type=int, choices=range(1, 6), help="只检查指定卷（1–5）。")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="项目根目录；默认是 scripts 上一级，成品为根目录 BookN.pdf。")
    parser.add_argument("--outline", type=Path, help="原纲要路径；默认从项目根目录读取。")
    args = parser.parse_args()
    root = args.root.resolve()
    outline = args.outline.resolve() if args.outline else root / "几何学计划纲要.md"
    try:
        companion = runpy.run_path(str(Path(__file__).with_name("Check-Outline.py")))
        nodes = companion["parse_outline"](outline)
        planned_headings = companion["planned_headings"]
        pdf_inline_title = companion["pdf_inline_title"]
    except Exception as exc:
        print(f"FAIL: 无法读取原纲要结构：{exc}", file=sys.stderr)
        return 1
    failures = []
    books = [args.book] if args.book else list(range(1, 6))
    for book in books:
        try:
            errors, stats = check_book(root, book, [node for node in nodes if node.book == book],
                                      planned_headings, pdf_inline_title)
            print(stats)
            failures.extend(f"Book{book}: {error}" for error in errors)
        except Exception as exc:
            failures.append(f"Book{book}: {exc}")
    if failures:
        print(f"FAIL: {len(failures)} 项 PDF 问题。", file=sys.stderr)
        for failure in failures[:20]:
            print(f"- {failure}", file=sys.stderr)
        if len(failures) > 20:
            print(f"- 其余 {len(failures) - 20} 项省略；修复后重新检查。", file=sys.stderr)
        return 1
    print("PASS: PDF 编号、标题、选读星号、书签层级及全部目的页与纲要一致；"
          "书签层级覆盖小节；封面稿件状态与源码一致。此检查不代表数学审核。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
