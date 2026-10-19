#!/usr/bin/env python3
"""Read-only checks for the geometry outline and its five-volume TeX skeleton.

Uses Python's standard library only.  By default, both the project and the
outline are found relative to this script, so the project can be moved intact.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import os
from pathlib import Path, PurePosixPath
import re
import sys


ORDINALS = {c: n for n, c in enumerate("一二三四五六七八九十", 1)}
BOOK_HEADING = re.compile(r"^# 第([一二三四五])卷[\s　]+(.+)$")
PART_HEADING = re.compile(r"^# 第([一二三四五六七八九十])编[\s　]+(.+)$")
CHAPTER_HEADING = re.compile(r"^## 第(\d+)章(\*)?[\s　]+(.+)$")
SECTION_HEADING = re.compile(r"^### (\d+)\.(\d+)(\*)?[\s　]+(.+)$")
APPENDICES_HEADING = re.compile(r"^# 第([一二三四五])卷附录$")
APPENDIX_HEADING = re.compile(r"^## 附录 ([A-Z])[\s　]+(.+)$")
COMMAND_ARITY = {
    "BookPart": 2, "chapter": 1, "OptionalChapter": 2,
    "section": 1, "subsection": 1, "OptionalSection": 2, "BookChapterNumber": 1,
    "label": 1, "input": 1, "include": 1,
}


@dataclass
class Node:
    kind: str
    book: int
    number: int | str
    title: str
    line: int
    heading: str
    path: PurePosixPath
    parent: PurePosixPath | None
    optional: bool = False
    label: str = ""
    body: list[str] = field(default_factory=list)


@dataclass
class Command:
    name: str
    args: list[str]
    star: bool
    offset: int


class CheckError(ValueError):
    pass


def read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def tex_title(title: str) -> str:
    # Typeset symbols as math while retaining the exact Unicode PDF title.
    replacements = (
        ("d₂", r"\texorpdfstring{\(\mathrm{d}_2\)}{d₂}"),
        ("Lᵖ", r"\texorpdfstring{\(L^p\)}{Lᵖ}"),
        ("L²", r"\texorpdfstring{\(L^2\)}{L²}"),
        # ASCII accent commands avoid active combining-character tokens in aux labels.
        ("∂∂̄", r"\texorpdfstring{\(\partial\bar{\partial}\)}{∂\={∂}}"),
        ("∂̄", r"\texorpdfstring{\(\bar{\partial}\)}{\={∂}}"),
    )
    # A single replacement pass avoids changing an earlier bookmark branch.
    mapping = dict(replacements)
    pattern = "|".join(re.escape(source) for source, _ in replacements)
    return re.sub(pattern, lambda match: mapping[match[0]], title)


def planned_headings(node: Node) -> list[tuple[str, str]]:
    """Return the numbered headings represented by literal outline bullets.

    Explanatory prose is deliberately excluded: in particular, the continuous
    computation in II.10.6 does not acquire an invented internal heading.
    """
    headings: list[tuple[str, str]] = []
    if node.kind == "section":
        for line in node.body:
            if match := re.fullmatch(r"\* (.+)", line):
                headings.append(("subsection", match[1]))
    elif node.kind == "appendix":
        for line in node.body:
            if match := re.fullmatch(r"\* \*\*(.+)\*\*", line):
                headings.append(("section", match[1]))
            elif match := re.fullmatch(r"  \* (.+)", line):
                headings.append(("subsection", match[1]))
    return headings



def pdf_inline_title(text: str) -> str:
    """Readable Unicode alternatives for the outline's inline formulas."""
    formulas = {
        r"X\to\Omega\Sigma X": "X→ΩΣX",
        r"(n-1)": "(n−1)", r"i-n": "i−n",
        r"\operatorname{Gr}(2,4)": "Gr(2,4)",
        r"\mathbb{CP}^1": "CP¹", r"X\times S^2": "X×S²",
        r"K^0(X\times S^2)": "K⁰(X×S²)",
        r"m": "m", r"W^{k,p}": "W^{k,p}", r"kp>m": "kp>m",
        r"\mathbb P^1\setminus\{0,1,\infty\}": "P¹∖{0,1,∞}",
        r"\operatorname{Spec}_S\operatorname{Sym}(E^\vee)": "Spec_S Sym(E∨)",
        r"R\rightrightarrows U": "R⇉U", r"U\times_XU": "U×_X U",
        r"f_*\mathcal O_X": "f_*O_X",
        r"Y^\prime=\operatorname{Spec}_Y(f_*\mathcal O_X)": "Y′=Spec_Y(f_*O_X)",
        r"\operatorname{Gr}(2,4)\subset\mathbb P^5": "Gr(2,4)⊂P⁵",
        r"\mathcal M_{0,4}\simeq\mathbb P^1\setminus\{0,1,\infty\}": "M_{0,4}≃P¹∖{0,1,∞}",
        r"\overline{\mathcal M}_{0,4}\simeq\mathbb P^1": "M̄_{0,4}≃P¹",
    }
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\$([^$]+)\$", lambda match: formulas[match[1]], text)


def pdf_title_tex(text: str) -> str:
    """Escape PDF alternatives and keep active Unicode out of aux labels."""
    greek = {
        "Λ": "CapitalLambda", "Ω": "Omega", "Σ": "CapitalSigma",
        "δ": "Delta", "ε": "Epsilon", "θ": "Theta", "ι": "Iota",
        "μ": "Mu", "π": "Pi", "ω": "SmallOmega", "ℓ": "Ell",
    }
    special = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
               "#": r"\#", "$": r"\$", "%": r"\%", "&": r"\&",
               "_": r"\_", "^": r"\textasciicircum{}", "~": r"\textasciitilde{}"}
    # Combining macrons must not become active tokens in auxiliary files.
    pieces = []
    for char in text:
        if char == "\u0304" and pieces:
            pieces[-1] = r"\={" + pieces[-1] + "}"
        else:
            pieces.append((r"\GeometryPdf" + greek[char] + "{}")
                          if char in greek else special.get(char, char))
    return "".join(pieces)


def tex_inline_title(text: str) -> str:
    """Typeset an outline bullet without changing its mathematical meaning.

    Existing inline TeX is protected before prose escaping.  The explicit
    formulas cover the outline's abbreviated, non-TeX notation; the remaining
    Unicode symbols are converted individually in text fragments only.
    Mathematical titles include readable PDF alternatives for bookmarks.
    """
    pdf_text = pdf_inline_title(text)
    text = text.replace("**", "").replace("`", "")
    formulas = {
        "ι_XH ω=dH": r"\iota_{X_H}\omega=\mathrm{d}H",
        "A_H=−∫u*ω−∫Hdt": r"A_H=-\int u^*\omega-\int H\,\mathrm{d}t",
        "∂su+J(∂tu−X_H)=0": r"\partial_su+J(\partial_tu-X_H)=0",
        "g(u,v)=ω(u,Jv)": r"g(u,v)=\omega(u,Jv)",
        "S²×T²ⁿ⁻²": r"S^2\times T^{2n-2}",
        "Hilbᵈ(A¹)": r"\operatorname{Hilb}^d(\mathbb A^1)",
        "Hom(I,O_Z)": r"\operatorname{Hom}(I,\mathcal O_Z)",
        "Rᵠf_*": r"R^q f_*",
        "W^{m,p}": r"W^{m,p}",
        "k[t²,t³]": r"k[t^2,t^3]",
        "T¹⁰": r"\mathrm{T}^{1,0}", "T⁰¹": r"\mathrm{T}^{0,1}",
        "W¹ᵖ": r"W^{1,p}",
        "ω=−dθ": r"\omega=-\mathrm{d}\theta", "dω=0": r"\mathrm{d}\omega=0",
        "d²=0": r"\mathrm{d}^2=0", "p>2": r"p>2", "n≥3": r"n\ge3", "R≤r": r"R\le r",
        "Morse(−H)": r"\operatorname{Morse}(-H)", "e−1": r"e-1", "−1": r"-1",
        "[ω]": r"[\omega]", "R₁+S₂": r"R_1+S_2",
        "∂∂̄": r"\partial\bar{\partial}", "∂̄": r"\bar{\partial}",
        "K⁰": r"K^0", "Lᵖ": r"L^p", "L²": r"L^2", "L¹": r"L^1",
        "C⁰": r"C^0", "C¹": r"C^1", "Cʳ": r"C^r", "H¹(T)": r"H^1(\mathrm{T})", "H²(T)": r"H^2(\mathrm{T})",
        "H¹": r"H^1", "H²": r"H^2", "Hⁱ": r"H^i", "Extⁿ⁻ⁱ": r"\operatorname{Ext}^{n-i}",
        "Ext¹": r"\operatorname{Ext}^1", "Ext²": r"\operatorname{Ext}^2",
        "Pic⁰": r"\operatorname{Pic}^0", "P¹": r"\mathbb P^1",
        "N¹": r"N^1", "N₁": r"N_1", "R₁": r"R_1", "S₂": r"S_2", "Sᵣ": r"S_r",
        "sl₂": r"\mathfrak{sl}_2", "G₂": r"G_2", "c₁": r"c_1", "m₀": r"m_0",
        "μₙ": r"\mu_n", "π₂": r"\pi_2", "A∞": r"A_\infty",
        "∂": r"\partial", "ω": r"\omega", "δ": r"\delta",
        "ε": r"\varepsilon", "θ": r"\theta", "ι": r"\iota",
        "μ": r"\mu", "π": r"\pi",
        "Λ": r"\Lambda", "Ω": r"\Omega", "ℓ": r"\ell",
    }
    special = {
        "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
        "#": r"\#", "$": r"\$", "%": r"\%", "&": r"\&",
        "_": r"\_", "^": r"\textasciicircum{}", "~": r"\textasciitilde{}",
    }
    pattern = re.compile("|".join(re.escape(key) for key in sorted(formulas, key=len, reverse=True)))

    def prose(fragment: str) -> str:
        pieces: list[str] = []
        previous = 0
        for match in pattern.finditer(fragment):
            pieces.append("".join(special.get(char, char) for char in fragment[previous:match.start()]))
            pieces.append(r"\(" + formulas[match[0]] + r"\)")
            previous = match.end()
        pieces.append("".join(special.get(char, char) for char in fragment[previous:]))
        return "".join(pieces)

    result: list[str] = []
    for fragment in re.split(r"(\$[^$\n]*\$)", text):
        if len(fragment) >= 2 and fragment.startswith("$") and fragment.endswith("$"):
            result.append(r"\(" + fragment[1:-1] + r"\)")
        else:
            result.append(prose(fragment))
    rendered = "".join(result)
    if "\\" in rendered:
        return r"\texorpdfstring{" + rendered + "}{" + pdf_title_tex(pdf_text) + "}"
    return rendered


def parse_outline(path: Path) -> list[Node]:
    lines = read_utf8(path).splitlines()
    starts = [i for i, line in enumerate(lines) if BOOK_HEADING.fullmatch(line)]
    ends = [i for i, line in enumerate(lines) if line == "# 建议阅读层次"]
    if not starts or not ends or starts[0] >= ends[0]:
        raise CheckError("找不到正式纲要范围：第一卷至‘建议阅读层次’之前。")
    start, end = starts[0], ends[0]
    nodes: list[Node] = []
    book = 0
    part = 0
    chapter = 0
    in_appendices = False
    book_path = part_path = chapter_path = appendices_path = None

    for index in range(start, end):
        line = lines[index]
        if not re.match(r"^#{1,3} ", line):
            continue
        kind = ""
        number: int | str = 0
        title = ""
        optional = False
        label = ""
        parent = None
        if match := BOOK_HEADING.fullmatch(line):
            book = ORDINALS[match[1]]
            part = chapter = 0
            in_appendices = False
            kind, number, title = "book", book, match[2]
            book_path = PurePosixPath(f"Book{book}/Book{book}.tex")
            node_path = book_path
        elif match := PART_HEADING.fullmatch(line):
            if not book or in_appendices:
                raise CheckError(f"纲要第 {index + 1} 行：编没有所属正文卷。")
            part = ORDINALS[match[1]]
            chapter = 0
            kind, number, title = "part", part, match[2]
            part_path = PurePosixPath(f"Book{book}/Part{part:02}/Part{part:02}.tex")
            node_path, parent = part_path, book_path
            label = f"g{book}:part:{part:02}"
        elif match := CHAPTER_HEADING.fullmatch(line):
            if not part or in_appendices:
                raise CheckError(f"纲要第 {index + 1} 行：章没有所属编。")
            chapter = int(match[1])
            kind, number, title = "chapter", chapter, match[3]
            optional = bool(match[2])
            chapter_path = part_path.parent / f"Chapter{chapter:02}" / f"Chapter{chapter:02}.tex"
            node_path, parent = chapter_path, part_path
            label = f"g{book}:ch:{chapter:02}"
        elif match := SECTION_HEADING.fullmatch(line):
            if not chapter or in_appendices or int(match[1]) != chapter:
                raise CheckError(f"纲要第 {index + 1} 行：节号与所属章不一致。")
            section = int(match[2])
            kind, number, title = "section", section, match[4]
            optional = bool(match[3])
            node_path = chapter_path.parent / f"Section{chapter:02}{section:02}.tex"
            parent = chapter_path
            label = f"g{book}:sec:{chapter:02}{section:02}"
        elif match := APPENDICES_HEADING.fullmatch(line):
            if ORDINALS[match[1]] != book:
                raise CheckError(f"纲要第 {index + 1} 行：附录卷号不一致。")
            in_appendices = True
            kind, number, title = "appendices", book, line[2:]
            appendices_path = PurePosixPath(f"Book{book}/Appendices/Appendices.tex")
            node_path, parent = appendices_path, book_path
        elif match := APPENDIX_HEADING.fullmatch(line):
            if not in_appendices:
                raise CheckError(f"纲要第 {index + 1} 行：附录没有入口。")
            kind, number, title = "appendix", match[1], match[2]
            node_path = appendices_path.parent / f"Appendix{number}" / f"Appendix{number}.tex"
            parent = appendices_path
            label = f"g{book}:app:{number}"
        else:
            raise CheckError(f"纲要第 {index + 1} 行：无法识别正式结构标题：{line}")
        nodes.append(Node(kind, book, number, title, index + 1, line,
                          node_path, parent, optional, label))

    for position, node in enumerate(nodes):
        following = nodes[position + 1].line - 1 if position + 1 < len(nodes) else end
        node.body = lines[node.line:following]

    def consecutive(kind: str, group_key, start_at: int = 1) -> None:
        groups = defaultdict(list)
        for node in nodes:
            if node.kind == kind:
                groups[group_key(node)].append(node)
        for values in groups.values():
            numbers = [ord(str(n.number)) - ord("A") + 1 if kind == "appendix"
                       else int(n.number) for n in values]
            if numbers != list(range(start_at, start_at + len(numbers))):
                raise CheckError(f"纲要第 {values[0].line} 行起：{kind} 编号不连续。")

    consecutive("book", lambda n: 0)
    consecutive("part", lambda n: n.book)
    consecutive("chapter", lambda n: n.book)
    consecutive("section", lambda n: n.parent)
    consecutive("appendix", lambda n: n.book)
    if len({n.path for n in nodes}) != len(nodes):
        raise CheckError("纲要结构生成了重复的源文件路径。")
    return nodes


def strip_comments(source: str) -> str:
    result = []
    for line in source.splitlines(keepends=True):
        cut = len(line)
        for position, char in enumerate(line):
            if char == "%":
                backslashes = 0
                cursor = position - 1
                while cursor >= 0 and line[cursor] == "\\":
                    backslashes += 1
                    cursor -= 1
                if backslashes % 2 == 0:
                    cut = position
                    break
        result.append(line[:cut] + ("\n" if cut < len(line) else ""))
    return "".join(result)


def braced(source: str, offset: int) -> tuple[str, int]:
    while offset < len(source) and source[offset].isspace():
        offset += 1
    if offset >= len(source) or source[offset] != "{":
        raise CheckError("需要花括号参数。")
    start = offset + 1
    depth = 1
    offset += 1
    while offset < len(source):
        if source[offset] == "\\":
            offset += 2
            continue
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start:offset], offset + 1
        offset += 1
    raise CheckError("花括号参数没有闭合。")


def commands(source: str) -> list[Command]:
    found = []
    for match in re.finditer(r"\\([A-Za-z]+)(\*)?", source):
        name = match[1]
        if name not in COMMAND_ARITY:
            continue
        offset = match.end()
        while offset < len(source) and source[offset].isspace():
            offset += 1
        # Standard chapter/section/subsection commands may carry a short TOC title.
        if offset < len(source) and source[offset] == "[":
            end = source.find("]", offset + 1)
            if end < 0:
                raise CheckError(f"\\{name} 的可选参数没有闭合。")
            offset = end + 1
        args = []
        try:
            for _ in range(COMMAND_ARITY[name]):
                arg, offset = braced(source, offset)
                args.append(arg)
        except CheckError:
            # Macro definitions may refer to these commands without executing
            # them.  Actual skeleton files only use braced, literal arguments.
            if name in ("input", "include"):
                raise CheckError(f"\\{name} 必须使用可解析的花括号字面路径。")
            continue
        found.append(Command(name, args, bool(match[2]), match.start()))
    return found


class Checker:
    def __init__(self, root: Path, nodes: list[Node]):
        self.root = root.resolve()
        self.nodes = nodes
        self.absolute_paths = {n.path: (self.root / Path(n.path)).resolve() for n in nodes}
        self.errors: list[str] = []
        self.texts: dict[Path, str] = {}
        self.parsed: dict[Path, list[Command]] = {}
        self.input_targets: dict[tuple[int, Path], list[Path]] = {}
        self.visited: set[Path] = set()

    def error(self, path: Path | PurePosixPath, message: str) -> None:
        try:
            display = Path(path).relative_to(self.root).as_posix()
        except ValueError:
            display = str(path)
        self.errors.append(f"{display}: {message}")

    def load(self, path: Path) -> str | None:
        path = path.resolve()
        if path in self.texts:
            return self.texts[path]
        if not path.is_file():
            self.error(path, "源文件不存在。")
            return None
        try:
            source = read_utf8(path)
            parsed = commands(strip_comments(source))
        except (OSError, UnicodeError, CheckError) as exc:
            self.error(path, str(exc))
            return None
        self.texts[path], self.parsed[path] = source, parsed
        return source

    def node_check(self, node: Node) -> None:
        path = self.absolute_paths[node.path]
        source = self.load(path)
        if source is None:
            return
        lines = source.splitlines()
        title_comment = f"% 纲要标题：{node.heading}"
        location_comment = f"% 纲要位置：几何学计划纲要.md，第 {node.line} 行"
        if lines.count(title_comment) != 1:
            self.error(path, f"应恰有一条原纲要元数据：{title_comment}")
        if sum(line.removesuffix("。") == location_comment for line in lines) != 1:
            self.error(path, f"应恰有一条原纲要元数据：{location_comment}")
        starts = [i for i, line in enumerate(lines) if line == "% 纲要内容开始"]
        ends = [i for i, line in enumerate(lines) if line == "% 纲要内容结束"]
        if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
            self.error(path, "需要唯一且闭合的‘纲要内容开始/结束’注释块。")
        else:
            actual = lines[starts[0] + 1:ends[0]]
            expected = ["% " + line for line in node.body]
            if actual != expected:
                mismatch = next((i for i, (left, right) in enumerate(zip(actual, expected))
                                 if left != right), min(len(actual), len(expected)))
                self.error(path, f"纲要原文注释块不完整或改动：原纲要第 {node.line + 1 + mismatch} 行附近。")
        self.root_check(path, node.book, optional=node.kind == "book")
        parsed = self.parsed[path]
        structural = [c for c in parsed if c.name in {
            "BookPart", "chapter", "OptionalChapter", "section", "OptionalSection"}
            and not (node.kind == "appendix" and c.name == "section")]
        expected_name = {
            "part": "BookPart", "chapter": "OptionalChapter" if node.optional else "chapter",
            "appendix": "chapter", "section": "OptionalSection" if node.optional else "section",
        }.get(node.kind)
        if expected_name:
            expected_args = [tex_title(node.title)]
            if node.kind == "part" or node.optional:
                expected_args.append(node.label)
            if len(structural) != 1 or structural[0].name != expected_name or structural[0].star or structural[0].args != expected_args:
                self.error(path, f"结构命令、标题或选读标记应为 \\{expected_name}" + "".join("{" + arg + "}" for arg in expected_args))
        elif structural:
            self.error(path, "卷主文件或附录入口不应额外声明编、章、节。")
        internal = [c for c in parsed if c.name == "subsection"
                    or (node.kind == "appendix" and c.name == "section")]
        expected_internal = [(level, tex_inline_title(title))
                             for level, title in planned_headings(node)]
        actual_internal = [(c.name, c.args[0]) for c in internal]
        if actual_internal != expected_internal:
            mismatch = next((i for i, (actual, expected) in enumerate(zip(actual_internal, expected_internal))
                             if actual != expected), min(len(actual_internal), len(expected_internal)))
            if mismatch < len(expected_internal):
                level, title = expected_internal[mismatch]
                self.error(path, f"计划小节标题第 {mismatch + 1} 项缺失、重复、顺序或文字不符，应为 \\{level}{{{title}}}。")
            else:
                self.error(path, "出现原纲要没有的额外小节标题。")
        if any(c.star for c in internal):
            self.error(path, "计划小节及附录主题组必须使用编号标题命令，以同步正文、目录和书签。")
        if node.kind in ("chapter", "section", "appendix"):
            labels = [c for c in parsed if c.name == "label" and c.args == [node.label]]
            if node.optional and labels:
                self.error(path, "选读命令已在第二参数定义稳定标签，不应重复声明 \\label。")
            elif not node.optional and len(labels) != 1:
                self.error(path, f"应恰有一个稳定标签 \\label{{{node.label}}}。")
            elif labels and structural and labels[0].offset < structural[0].offset:
                self.error(path, "稳定标签必须跟在结构命令之后。")
        numbers = [c for c in parsed if c.name == "BookChapterNumber"]
        if node.kind == "chapter":
            if len(numbers) != 1 or numbers[0].args != [node.label]:
                self.error(path, f"章号声明应为 \\BookChapterNumber{{{node.label}}}。")
            elif structural and numbers[0].offset < structural[0].offset:
                self.error(path, "章号声明必须跟在章标题之后。")
        elif numbers and (node.kind != "appendix" or len(numbers) != 1 or numbers[0].args != [node.label]):
            self.error(path, "出现不属于本节点的章号声明。")
        if node.kind == "book":
            code = strip_comments(source)
            match = re.search(r"\\(?:newcommand|renewcommand)\s*\{\\BookTitle\}\s*", code)
            if not match:
                self.error(path, "缺少 \\BookTitle 卷标题定义。")
            else:
                try:
                    title, _ = braced(code, match.end())
                    if title != tex_title(node.title):
                        self.error(path, f"\\BookTitle 应为‘{node.title}’。")
                except CheckError as exc:
                    self.error(path, str(exc))

    def root_check(self, path: Path, book: int, optional: bool = False) -> None:
        source = self.texts[path]
        roots = re.findall(r"^%\s*!TeX\s+root\s*=\s*(.*?)\s*$", source, flags=re.MULTILINE | re.IGNORECASE)
        if optional and not roots:
            return
        main = self.root / f"Book{book}" / f"Book{book}.tex"
        expected = os.path.relpath(main, path.parent).replace("\\", "/")
        if len(roots) != 1 or roots[0].replace("\\", "/") != expected:
            self.error(path, f"TeX root 应为相对本卷主文件的路径：{expected}")

    def walk(self, path: Path, book: int, active: set[Path], reached: set[Path]) -> None:
        path = path.resolve()
        if path in active:
            self.error(path, "发现循环输入。")
            return
        if path in reached:
            return
        reached.add(path)
        if self.load(path) is None:
            return
        self.visited.add(path)
        active = active | {path}
        targets = []
        book_root = self.root / f"Book{book}"
        for command in self.parsed[path]:
            if command.name not in ("input", "include"):
                continue
            value = command.args[0]
            if "#" in value or "\\" in value or not value.strip():
                self.error(path, f"不可解析的输入路径：{value}")
                continue
            relative = Path(value)
            if relative.is_absolute():
                self.error(path, f"输入必须采用相对卷目录的路径：{value}")
                continue
            if not relative.suffix:
                relative = relative.with_suffix(".tex")
            target = (book_root / relative).resolve()
            if not target.is_relative_to(self.root):
                self.error(path, f"输入超出了项目根目录：{value}")
                continue
            if target.is_relative_to(self.root / "Shared") and not value.startswith("../Shared/"):
                self.error(path, f"Shared 输入应相对卷目录使用 ../Shared/：{value}")
            targets.append(target)
            self.walk(target, book, active, reached)
        self.input_targets[(book, path)] = targets

    def run(self) -> None:
        for node in self.nodes:
            self.node_check(node)
        books = sorted({n.book for n in self.nodes})
        for book in books:
            reached: set[Path] = set()
            main = self.root / f"Book{book}" / f"Book{book}.tex"
            self.walk(main, book, set(), reached)
            expected_nodes = [n for n in self.nodes if n.book == book]
            node_targets = {self.absolute_paths[n.path] for n in expected_nodes}
            for node in expected_nodes:
                absolute = self.absolute_paths[node.path]
                if absolute not in reached:
                    self.error(node.path, "没有从本卷主文件输入链到达。")
                children = [self.absolute_paths[n.path] for n in expected_nodes if n.parent == node.path]
                actual = self.input_targets.get((book, absolute), [])
                actual_children = [p for p in actual if p in node_targets]
                if actual_children != children:
                    self.error(node.path, "直接输入的纲要子节点缺失、重复、顺序不符或跨层输入。")
            for path in (self.root / f"Book{book}").rglob("*.tex"):
                if path.resolve() not in reached:
                    self.error(path, "孤立 TeX 文件：未从本卷主文件输入链到达。")
                elif path.resolve() not in node_targets:
                    if self.load(path.resolve()) is not None:
                        self.root_check(path.resolve(), book)
        labels: dict[str, list[Path]] = defaultdict(list)
        for path in sorted(self.visited):
            for command in self.parsed[path]:
                defining_macros = ("BookPart", "OptionalChapter", "OptionalSection")
                value = command.args[1] if command.name in defining_macros else command.args[0]
                if command.name in ("label", *defining_macros) and "#" not in value and "\\" not in value:
                    labels[value].append(path)
        for label, occurrences in labels.items():
            if len(occurrences) > 1:
                self.error(occurrences[0], f"重复标签 {label}：" + "、".join(p.relative_to(self.root).as_posix() for p in occurrences))


def main() -> int:
    parser = argparse.ArgumentParser(description="只读核对几何学纲要、源文件结构、注释、标签和输入链。")
    parser.add_argument("-Book", "--book", "-b", type=int, choices=range(1, 6), help="只检查指定卷（1–5）。")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="项目根目录，默认是 scripts 上一级。")
    parser.add_argument("--outline", type=Path, help="纲要原文件，默认是项目根目录的几何学计划纲要.md。")
    args = parser.parse_args()
    root = args.root.resolve()
    outline = args.outline.resolve() if args.outline else root / "几何学计划纲要.md"
    try:
        nodes = parse_outline(outline)
    except (OSError, UnicodeError, CheckError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if args.book:
        nodes = [node for node in nodes if node.book == args.book]
    checker = Checker(root, nodes)
    checker.run()
    for book in sorted({n.book for n in nodes}):
        counts = Counter(n.kind for n in nodes if n.book == book)
        optional_chapters = sum(n.optional for n in nodes if n.book == book and n.kind == "chapter")
        optional_sections = sum(n.optional for n in nodes if n.book == book and n.kind == "section")
        print(f"Book{book}: {counts['part']} 编，{counts['chapter']} 章（选读 {optional_chapters}），"
              f"{counts['section']} 节（选读 {optional_sections}），{counts['appendix']} 附录。")
    if checker.errors:
        print(f"FAIL: {len(checker.errors)} 项结构问题。", file=sys.stderr)
        for error in checker.errors[:20]:
            print(f"- {error}", file=sys.stderr)
        if len(checker.errors) > 20:
            print(f"- 其余 {len(checker.errors) - 20} 项省略；修复后重新检查。", file=sys.stderr)
        return 1
    print(f"PASS: {len(nodes)} 个纲要节点；{len(checker.visited)} 个可达 TeX 源文件。"
          "结构与原文注释一致；不代表正文完成、数学审核或编译通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
