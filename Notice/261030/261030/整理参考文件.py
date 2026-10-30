import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import pdfplumber
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "附件：《2026级新生学业知识竞答活动参考文件》.pdf"
COPY = ROOT / SOURCE.name
SECTIONS = [
    ("01-考试违规与作弊认定.md", "学生考试违规、作弊的认定办法", 3, 6, "违规；作弊；严重作弊；手机；替考；雷同；认定"),
    ("02-学籍管理实施细则-2025修订.md", "学生学籍管理实施细则（2025年修订）", 7, 20, "注册；学制；请假；考勤；成绩；GPA；补考；缓考；免修；转专业；休学；退学；毕业"),
    ("03-学士学位授予细则.md", "本科毕业生学士学位授予细则", 21, 23, "学位；学位评定委员会；学位授予条件；学位授予程序；不授予；撤销；复核"),
    ("04-学科竞赛管理规定.md", "学科竞赛管理规定", 24, 31, "梯队；级别；团队；成绩奖励赋分；学分认定；奖金；经费"),
    ("05-体育艺术竞赛奖励办法.md", "学生体育、艺术类竞赛成果奖励办法（试行）", 32, 36, "体育；艺术；名次；GPA；现金奖励；破纪录；集体项目"),
    ("06-劳动教育学分认定.md", "劳动教育学分认定管理办法", 37, 39, "劳动教育；积分；学分；志愿服务；勤工助学；社会实践；认定部门"),
    ("07-课外教育选修学分.md", "课外教育选修学分实施细则（试行）", 40, 45, "课外教育；选修学分；活动章；讲座；社会实践；资格证书；第二课堂；申请表"),
]


def compact(text):
    return re.sub(r"\s+", "", text)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section_for(page):
    return next((s for s in SECTIONS if s[2] <= page <= s[3]), None)


def body_text(text, number):
    lines = text.splitlines()
    if lines and lines[-1].strip() == str(number):
        lines.pop()
    return "\n".join(lines).strip()


def main():
    assert SOURCE.is_file(), SOURCE
    if COPY.exists():
        assert digest(SOURCE) == digest(COPY), "目标PDF与原件不同，停止覆盖"
    else:
        shutil.copy2(SOURCE, COPY)
    reader = PdfReader(SOURCE)
    assert len(reader.pages) == 45
    records = []
    articles = []
    with pdfplumber.open(SOURCE) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            assert text.strip(), f"第{number}页无可提取文字"
            section = section_for(number)
            tables = [
                {"bbox": list(table.bbox), "cells": table.extract()}
                for table in page.find_tables()
            ]
            record = {
                "page": number,
                "section": section[1] if section else ("封面" if number == 1 else "目录"),
                "file": section[0] if section else None,
                "anchor": f"p{number:03d}",
                "text": text,
                "search_text": compact(text),
                "tables": tables,
            }
            records.append(record)
            for line in text.splitlines():
                normalized = compact(line)
                match = re.match(r"^(第[一二三四五六七八九十百零〇]+[条章])(.+)?", normalized)
                if match and section:
                    articles.append((section[0], number, match.group(1), (match.group(2) or "")[:45]))
            record["layout_text"] = (page.extract_text(layout=True) or "").strip() if tables else text

    jsonl = ROOT / "逐页索引.jsonl"
    jsonl.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    for filename, title, start, end, keywords in SECTIONS:
        parts = [
            f"# {title}\n\n",
            f"来源：[原始PDF]({COPY.name}#page={start})，第{start}—{end}页。\n\n",
            f"检索词：{keywords}。\n\n",
            "以下为PDF文字层提取内容，按页保留换行；含表格或文本框的页面采用文字布局提取，提取的单元格见`逐页索引.jsonl`的`tables`。\n\n",
        ]
        for record in records[start - 1:end]:
            number = record["page"]
            parts.append(f'<a id="p{number:03d}"></a>\n\n## 原文第{number}页\n\n')
            parts.append("```text\n" + body_text(record["layout_text"], number) + "\n```\n\n")
        (ROOT / filename).write_text("".join(parts), encoding="utf-8")

    index = [
        "# 2026级新生学业知识竞答活动参考文件：检索入口\n\n",
        "本目录按附件整理，保留全部45页文字及7份制度，不补充外部规定、不改写原文结论。\n\n",
        "## 文件与页码\n\n",
        "| 编号 | 制度文件 | PDF页码 | 关键词 |\n| --- | --- | --- | --- |\n",
    ]
    for n, (filename, title, start, end, keywords) in enumerate(SECTIONS, 1):
        index.append(f"| {n} | [{title}]({filename}) | {start}—{end} | {keywords} |\n")
    index.extend([
        "\n## 检索方法\n\n",
        "1. 根据上表选择制度，再按下方章节、条款索引定位页码。引用时写明制度名称、条款及PDF页码。\n",
        "2. 直接搜索Markdown可保留上下文；跨行关键词用`逐页索引.jsonl`的`search_text`字段，该字段移除了所有空白，原文保存在`text`。\n",
        "3. 查询金额、名次、学分和绩点时读取对应页的`tables`，结合该页正文与相邻页说明核对。表格可能跨页。\n",
        "4. 例如：`rg -n '补考|缓考|退学警示' 261030/02-*.md`；`rg -n '校园活动章至少2个|时长每10小时记1分' 261030/逐页索引.jsonl`。\n\n",
        "## 数据说明\n\n",
        f"- [原始PDF副本]({COPY.name})：45页，PDF物理页码与正文印刷页码一致；根目录附件保持原样。\n",
        "- [逐页索引.jsonl](逐页索引.jsonl)：每行一页，连续覆盖封面、目录及全部正文；字段为`page`、`section`、`file`、`anchor`、`text`、`search_text`、`tables`、`layout_text`。\n",
        "- `tables`保留pdfplumber识别出的13处候选表格区域（含第21、22页的单列表格/文本框），`bbox`为PDF坐标范围，`cells`为二维单元格数组。`null`表示提取器未给出独立单元格，常见于合并区域；空字符串表示提取为空，不擅自填充或推断。\n",
        "- `layout_text`保留含表格页的文字排列；文字布局仅为检索辅助，不能代替PDF中合并行列的含义。\n",
        "- 提取清除了Markdown正文页末的独立页码，保留每页标题及原始JSON文字。没有OCR、截图或视觉复核；图表行列关联及公式排版存在文字层提取限制，关键数字应回查原PDF。\n",
        "- [整理脚本](整理参考文件.py)用于复现提取与检查，运行需要pypdf与pdfplumber。\n\n",
        "## 章节与条款位置\n\n",
        "标题摘录用于定位，条款正文以链接页面为准；跨页条款需继续读取后续页面。\n\n",
    ])
    for filename, title, start, end, _ in SECTIONS:
        index.append(f"### {title}\n\n| 章节/条款 | 开头摘录 | 原文页码 |\n| --- | --- | --- |\n")
        for fn, page, label, excerpt in articles:
            if fn == filename:
                index.append(f"| {label} | {excerpt} | [第{page}页]({filename}#p{page:03d}) |\n")
        index.append("\n")
    index.append("## 表格及文本框位置\n\n| PDF页码 | 所属文件 | 本页识别区域数 |\n| --- | --- | --- |\n")
    for r in records:
        if r["tables"]:
            index.append(f'| [{r["page"]}]({r["file"]}#{r["anchor"]}) | {r["section"]} | {len(r["tables"])} |\n')
    (ROOT / "索引.md").write_text("".join(index), encoding="utf-8")

    restored = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
    assert [r["page"] for r in restored] == list(range(1, 46))
    assert digest(SOURCE) == digest(COPY)
    assert sum(end - start + 1 for _, _, start, end, _ in SECTIONS) == 43
    for r, page in zip(restored, reader.pages):
        assert r["search_text"] == compact(r["text"])
        assert Counter(r["search_text"]) == Counter(compact(page.extract_text()))
        assert Counter(r["search_text"]) == Counter(compact(r["layout_text"]))
        assert r["text"].splitlines()[-1].strip() == str(r["page"])
        assert "�" not in r["text"], f'第{r["page"]}页含替换字符'
        if r["file"]:
            document = (ROOT / r["file"]).read_text(encoding="utf-8")
            assert f'id="{r["anchor"]}"' in document
    for target in re.findall(r"\]\(([^)]+)\)", (ROOT / "索引.md").read_text(encoding="utf-8")):
        path, _, anchor = target.partition("#")
        assert (ROOT / path).is_file(), path
        if anchor:
            assert f'id="{anchor}"' in (ROOT / path).read_text(encoding="utf-8")
    for keyword in ["缓考", "退学警示", "劳动教育", "校园活动章至少2个"]:
        assert any(keyword in r["search_text"] for r in restored), keyword
    for _, title, start, end, keywords in SECTIONS:
        for keyword in keywords.split("；"):
            assert any(keyword in r["search_text"] for r in restored[start - 1:end]), (title, keyword)
    summary = {
        "status": "passed",
        "pages": len(restored),
        "documents": len(SECTIONS),
        "detected_table_regions": sum(len(r["tables"]) for r in restored),
        "table_pages": [r["page"] for r in restored if r["tables"]],
        "article_and_chapter_locations": len(articles),
        "source_sha256": digest(SOURCE),
        "copy_sha256": digest(COPY),
        "source_text_characters": sum(len(r["text"]) for r in restored),
        "pypdf_pdfplumber_character_counts_equal": True,
        "layout_character_counts_equal": True,
        "visual_review": False,
    }
    (ROOT / "验证结果.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
