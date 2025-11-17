# docx_utils.py

from docx import Document
from docx.shared import Pt


def build_docx_from_ga(ga_pairs, title: str = "培训考试题（含答案与原文引用）"):
    """
    ga_pairs: List[dict]，字段：
      id, question, ga_answer, difficulty, source_excerpt, source_locator, comment
    返回：python-docx 的 Document 对象
    """
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(11)

    # 标题
    doc.add_heading(title, level=1)

    # 一、试题（不含答案）
    doc.add_heading("一、试题（不含答案）", level=2)
    for idx, qa in enumerate(ga_pairs, start=1):
        q = (qa.get("question") or "").strip()
        p = doc.add_paragraph()
        p.add_run(f"{idx}. {q}")

    doc.add_page_break()

    # 二、参考答案与原文引用
    doc.add_heading("二、参考答案与原文引用", level=2)
    for idx, qa in enumerate(ga_pairs, start=1):
        q = (qa.get("question") or "").strip()
        a = (qa.get("ga_answer") or "").strip()
        difficulty = (qa.get("difficulty") or "").strip()
        source_excerpt = (qa.get("source_excerpt") or "").strip()
        locator = (qa.get("source_locator") or "").strip()
        comment = (qa.get("comment") or "").strip()

        doc.add_paragraph(f"{idx}. 题目：{q}")
        doc.add_paragraph(f"   【参考答案】{a}")
        if difficulty:
            doc.add_paragraph(f"   【难度】{difficulty}")
        if locator:
            doc.add_paragraph(f"   【来源定位】{locator}")
        if source_excerpt:
            doc.add_paragraph(f"   【原文摘录】{source_excerpt}")
        if comment:
            doc.add_paragraph(f"   【命题说明】{comment}")
        doc.add_paragraph("")  # 空行分隔

    return doc
