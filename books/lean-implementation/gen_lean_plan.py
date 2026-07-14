"""Generate 4-week Lean learning plan as PDF."""
from fpdf import FPDF

pdf = FPDF()
pdf.set_auto_page_break(auto=True, margin=12)
pdf.add_font("Deng", "", r"C:\Windows\Fonts\Deng.ttf")
pdf.add_font("Deng", "B", r"C:\Windows\Fonts\Dengb.ttf")

LM = 15
PW = 180
INDENT = LM + 5

def nl(h=3):
    pdf.ln(h)

def title(text):
    pdf.set_font("Deng", "B", 16)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(PW, 10, text, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(0, 0, 0)

def subtitle(text):
    pdf.set_font("Deng", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(PW, 6, text, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(0, 0, 0)

def section(text):
    if pdf.get_y() > pdf.h - 30:
        pdf.add_page()
    pdf.set_font("Deng", "B", 12)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(PW, 8, text, new_x="LMARGIN", new_y="NEXT")
    y = pdf.get_y()
    pdf.set_draw_color(44, 62, 80)
    pdf.line(LM, y, LM + PW, y)
    pdf.set_y(y + 2)
    pdf.set_text_color(0, 0, 0)

def bullet(text):
    pdf.set_font("Deng", "", 9)
    old_l = pdf.l_margin
    pdf.set_left_margin(INDENT)
    pdf.set_x(INDENT)
    pdf.multi_cell(PW - 5, 5, "-\u00a0" + text)
    pdf.set_left_margin(old_l)

def body(text):
    pdf.set_font("Deng", "", 9.5)
    old_l = pdf.l_margin
    pdf.set_left_margin(INDENT)
    pdf.set_x(INDENT)
    pdf.multi_cell(PW - 5, 5, text)
    pdf.set_left_margin(old_l)

def subheading(text):
    pdf.set_font("Deng", "B", 10)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(PW, 6, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

def phase_block(phase, subtitle_text, items, skills):
    subheading(phase + ": " + subtitle_text)
    for item in items:
        bullet(item)
    pdf.set_font("Deng", "", 8.5)
    pdf.set_text_color(100, 100, 100)
    pdf.set_x(INDENT)
    pdf.multi_cell(PW - 5, 4.5, "Skills: " + ", ".join(skills))
    pdf.set_text_color(0, 0, 0)
    nl(3)

# ===== PAGE 1 =====
pdf.add_page()
title("\u7cbe\u76ca\u5236\u9020\u5b66\u4e60\u8ba1\u5212")
subtitle("How to Implement Lean Manufacturing \u2014 4-Week Learning Path")
subtitle("\u300a\u5982\u4f55\u5b9e\u65bd\u7cbe\u76ca\u5236\u9020\u300b\u2014 Lonnie Wilson")
nl(4)

# Overview
pdf.set_font("Deng", "B", 11)
pdf.cell(PW, 7, "\u6982\u8ff0", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Deng", "", 9.5)
pdf.multi_cell(PW, 5, "\u57fa\u4e8e\u300a\u5982\u4f55\u5b9e\u65bd\u7cbe\u76ca\u5236\u9020\u300b\uff08Lonnie Wilson\uff0c335\u9875\uff09\u7684cangjie\u84b8\u998f\u7ed3\u679c\uff0c\u63d0\u53d6\u4e869\u4e2a\u53ef\u6267\u884c\u7684Hermes skills\u3002\u672c\u8ba1\u5212\u52064\u5468\uff0c\u6bcf\u5468\u805a\u7126\u4e0d\u540c\u4e3b\u9898\uff0c\u7ed3\u5408\u8bfb\u4e66 + skills + \u8bdd\u672f\u5e93 + \u5b66\u4e60\u7b14\u8bb0\u3002")
nl(4)

# Key resources
pdf.set_font("Deng", "B", 11)
pdf.cell(PW, 7, "\u5b66\u4e60\u8d44\u6e90", new_x="LMARGIN", new_y="NEXT")
bullet("\u4e66\u7c4d: How to Implement Lean Manufacturing (Lonnie Wilson, 2010)")
bullet("\u5b66\u4e60\u7b14\u8bb0: LEARNING_NOTE.md (\u4e2d\u6587 + \u82f1\u6587\u672f\u8bed)")
bullet("\u8bdd\u672f\u5e93: TALKING_POINTS.md (12\u6761\u8bdd\u672f\uff0c\u914d\u573a\u666f\u6807\u7b7e)")
bullet("Hermes Skills: 9\u4e2alean-* skills (\u53ef\u7528 / \u547d\u4ee4\u8c03\u7528)")
bullet("\u539f\u59cb PDF: ~/shared/Grad/Books/lean-implementation-tools.pdf")
nl(3)

# Practice approach
pdf.set_font("Deng", "B", 11)
pdf.cell(PW, 7, "\u5b66\u4e60\u65b9\u6cd5", new_x="LMARGIN", new_y="NEXT")
bullet("\u6bcf\u5b66\u5b8c\u4e00\u4e2askill\uff0c\u7528\u8bdd\u672f\u5e93\u5411Hermes\u590d\u8ff0\u6982\u5ff5\uff0c\u68c0\u67e5\u7406\u89e3\u7a0b\u5ea6")
bullet("\u91cf\u5316\u6280\u80fd\uff08kanban\u3001lead time\u3001\u5355\u5143\u8bbe\u8ba1\uff09\u505a\u4e66\u4e2d\u7684\u8ba1\u7b97\u7ec3\u4e60")
bullet("\u8bfb\u6848\u4f8b\u7814\u7a76\uff08Alpha Line\u3001Bravo Line\uff09\u7406\u89e3\u5b9e\u9645\u5e94\u7528")
bullet("\u6bcf\u5468\u7ed3\u675f\u65f6\u7528TALKING_POINTS.md\u81ea\u6d4b")
nl(3)

# Phase 1
section("Week 1: \u57fa\u7840 (Foundations)")
phase_block(
    "\u7b2c1\u6b65", "\u8bfbLEARNING_NOTE.md \u2014 \u5168\u666f\u6982\u89c8",
    ["\u4e86\u89e3\u7cbe\u76ca\u7684\u6838\u5fc3\u601d\u60f3\u3001\u4e5d\u5927\u65b9\u6cd5\u8bba\u3001\u5173\u952e\u672f\u8bed"],
    []
)
phase_block(
    "\u7b2c2\u6b65", "\u52a0\u8f7dleanskill: lean-house",
    ["\u7406\u89e3\u7cbe\u76ca\u5c4b\u7684\u5b8c\u6574\u7ed3\u6784\uff1a\u5c4b\u9876\uff08\u76ee\u6807\uff09\u3001\u5de6\u67f1\uff08JIT\uff09\u3001\u53f3\u67f1\uff08Jidoka\uff09\u3001\u5730\u57fa\uff08\u7a33\u5b9a\u6027+\u4eba\u5458\uff09",
     "\u8fd9\u662f\u7406\u89e3\u6240\u6709\u5176\u4ed6skills\u7684\u6846\u67b6"],
    ["lean-house"]
)
phase_block(
    "\u7b2c3\u6b65", "\u8bfb\u4e66Ch 2 + Ch 4",
    ["Ch 2: Lean Manufacturing and TPS \u2014 \u4e24\u5927\u652f\u67f1\uff08JIT + Jidoka\uff09\u3001\u4e03\u79cd\u6d6a\u8d39",
     "Ch 4: Lean Simplified \u2014 \u7cbe\u76ca\u7684\u4e09\u4e2a\u5c42\u6b21\uff08\u54f2\u5b66 \u2192 \u76ee\u6807 \u2192 \u5b9e\u65bd\uff09",
     "\u91cd\u70b9\u7406\u89e3Ohno\u7684\u4e09\u4e2a\u5173\u952e\u58f0\u660e"],
    ["lean-house"]
)
nl(2)

# Phase 2
section("Week 2: \u6838\u5fc3\u6982\u5ff5 (Core Concepts)")
phase_block(
    "\u7b2c4\u6b65", "\u52a0\u8f7d lean-lead-time-analysis",
    ["\u7406\u89e3\u4ea4\u4ed8\u5468\u671f\u5206\u89e3\uff1a\u52a0\u5de5 + \u7b49\u5f85 + \u642c\u8fd0 + \u6392\u961f",
     "\u6838\u5fc3\u6d1f\u5bdf\uff1a95-99%\u7684\u4ea4\u4ed8\u5468\u671f\u662f\u4e0d\u589e\u503c\u7684",
     "\u4e03\u79cd\u7f29\u77ed\u6280\u672f\uff1aSMED\u3001\u7f29\u5c0f\u6279\u91cf\u3001\u51cf\u5c11WIP\u3001TPM\u3001\u63d0\u5347\u8d28\u91cf\u3001\u5e73\u51c6\u5316\u3001\u6539\u5584\u5e03\u5c40"],
    ["lean-lead-time-analysis"]
)
phase_block(
    "\u7b2c5\u6b65", "\u52a0\u8f7d lean-kanban-calculation",
    ["\u770b\u677f\u8ba1\u7b97\u516c\u5f0f\uff1a\u770b\u677f\u6570\u91cf = (\u65e5\u9700\u6c42 \u00d7 \u4ea4\u4ed8\u5468\u671f \u00d7 \u5b89\u5168\u7cfb\u6570) / \u5bb9\u5668\u5bb9\u91cf",
     "\u4e09\u79cd\u5e93\u5b58\uff1a\u5468\u8f6c\u5e93\u5b58\u3001\u7f13\u51b2\u5e93\u5b58\u3001\u5b89\u5168\u5e93\u5b58",
     "\u505a\u4e66\u4e2dCh 3\u7684\u8ba1\u7b97\u7ec3\u4e60"],
    ["lean-kanban-calculation"]
)
phase_block(
    "\u7b2c6\u6b65", "\u52a0\u8f7d lean-four-strategies",
    ["\u56db\u7b56\u7565\uff1a\u5916\u90e8\u540c\u6b65 \u2192 \u5185\u90e8\u540c\u6b65 \u2192 \u521b\u5efa\u6d41 \u2192 \u5efa\u7acb\u62c9\u52a8",
     "\u4e94\u4e2a\u8bca\u65ad\u5de5\u5177\uff1a\u8282\u62cd\u8ba1\u7b97\u3001\u65f6\u95f4\u7814\u7a76\u3001\u5e73\u8861\u5206\u6790\u3001\u610f\u5927\u5229\u9762\u56fe\u3001\u4ef7\u503c\u6d41\u56fe",
     "\u4e03\u79cd\u6d6a\u8d39\uff1aTWO DIME"],
    ["lean-four-strategies", "lean-lead-time-analysis", "lean-kanban-calculation"]
)
nl(2)

# Phase 3
section("Week 3: \u5b9e\u65bd\u65b9\u6cd5 (Implementation)")
phase_block(
    "\u7b2c7\u6b65", "\u52a0\u8f7d lean-cultural-change",
    ["\u6587\u5316\u5148\u4e8e\u5de5\u5177\u2014\u2014\u4e09\u4e2a\u5fc5\u987b\u56de\u7b54\u201c\u662f\u201d\u7684\u95ee\u9898\uff1a\u9886\u5bfc\u529b\u3001\u52a8\u529b\u3001\u95ee\u9898\u89e3\u51b3",
     "TPS\u4e2d\u95ee\u9898\u662f\u7cfb\u7edf\u5f31\u70b9\uff0c\u4e0d\u662f\u4e2a\u4eba\u5931\u8d25",
     "\u5de5\u4eba\u53ef\u4ee5\u505c\u7ebf\u2014\u2014\u8fd9\u662f\u9769\u547d\u6027\u6982\u5ff5"],
    ["lean-cultural-change"]
)
phase_block(
    "\u7b2c8\u6b65", "\u52a0\u8f7d lean-project-prescription",
    ["\u516b\u6b65\u5904\u65b9\uff1a\u7cfb\u7edf\u8bc4\u4f30\uff081-3\uff09\u2192 \u4ef7\u503c\u6d41\u8bc4\u4f30\uff084-8\uff09",
     "\u5173\u952e\u539f\u5219\uff1a\u4e00\u6b21\u53ea\u505a\u4e00\u6761\u4ef7\u503c\u6d41",
     "\u5148\u4fdd\u62a4\u5ba2\u6237\uff0c\u518d\u6539\u5584"],
    ["lean-project-prescription", "lean-cultural-change"]
)
phase_block(
    "\u7b2c9\u6b65", "\u8bfb\u6848\u4f8b\u7814\u7a76",
    ["Ch 14: Alpha Line \u2014 \u5b8c\u6574\u7cbe\u76ca\u8f6c\u578b\u6848\u4f8b\uff0c\u4ea7\u80fd\u63d0\u534763%",
     "Ch 15: Bravo Line \u2014 \u4ea4\u4ed8\u5468\u671f\u7f29\u77ed\u548c\u65e9\u671f\u6536\u76ca",
     "\u7528TALKING_POINTS.md\u81ea\u6d4b"],
    []
)
nl(2)

# Phase 4
section("Week 4: \u8fdb\u9636 (Advanced)")
phase_block(
    "\u7b2c10\u6b65", "\u52a0\u8f7d lean-cellular-manufacturing",
    ["\u5355\u5143\u5316\u5236\u9020\u8bbe\u8ba1\uff1a\u6309\u4ea7\u54c1\u65cf\u5206\u7ec4\uff0cC/U\u5f62\u5e03\u5c40",
     "\u8bbe\u5907\u201c\u5408\u9002\u5c3a\u5bf8\u201d\uff0c\u4e0d\u662f\u8d8a\u5927\u8d8a\u597d",
     "\u64cd\u4f5c\u5458\u591a\u80fd\u5de5\uff0c\u5355\u4ef6\u6d41",
     "\u505aCh 13\u7684\u5355\u5143\u8bbe\u8ba1\u8ba1\u7b97\u7ec3\u4e60"],
    ["lean-cellular-manufacturing"]
)
phase_block(
    "\u7b2c11\u6b65", "\u52a0\u8f7d lean-constraint-management",
    ["\u74f6\u9888\u7ba1\u7406\u5faa\u73af\uff1a\u8bc6\u522b \u2192 \u5229\u7528 \u2192 \u4ece\u5c5e \u2192 \u63d0\u5347 \u2192 \u91cd\u590d",
     "\u7ea6\u675f\u4e0d\u4e00\u5b9a\u662f\u5de5\u4f4d\uff0c\u4e5f\u53ef\u80fd\u662f\u653f\u7b56\u7ea6\u675f",
     "\u4f4e\u6302\u679c\u5b50\uff1a\u74f6\u9888\u51cf\u5c11\u662f\u65e9\u671f\u6536\u76ca\u7684\u5173\u952e"],
    ["lean-constraint-management"]
)
phase_block(
    "\u7b2c12\u6b65", "\u52a0\u8f7d lean-sustaining-gains",
    ["\u4fee\u597d\u5b83\uff0c\u53ea\u4fee\u4e00\u6b21\u2014\u2014\u6807\u51c6\u5316 + \u5ba1\u8ba1",
     "\u5458\u5de5\u6d41\u52a8\u662f\u6700\u5927\u5a01\u80c1\u2014\u2014\u4e00\u5207\u90fd\u8981\u6587\u6863\u5316",
     "\u5148\u5de9\u56fa\u5f53\u524d\uff0c\u518d\u6269\u5c55\u65b0\u533a\u57df"],
    ["lean-sustaining-gains"]
)
phase_block(
    "\u590d\u4e60", "\u7efc\u5408\u590d\u4e60 + \u81ea\u6d4b",
    ["\u7528TALKING_POINTS.md\u768412\u6761\u8bdd\u672f\u81ea\u6d4b",
     "\u7528House of Lean\u6846\u67b6\u89e3\u91ca\u6574\u4e2a\u7cbe\u76ca\u7cfb\u7edf",
     "\u5c1d\u8bd5\u7528\u7cbe\u76ca\u8bed\u8a00\u5206\u6790\u4e00\u4e2a\u771f\u5b9e\u7684\u5236\u9020\u573a\u666f"],
    []
)

# Footer
nl(3)
pdf.set_draw_color(180, 180, 180)
y = pdf.get_y()
pdf.line(LM, y, LM + PW, y)
nl(2)
pdf.set_font("Deng", "", 9)
pdf.set_text_color(100, 100, 100)
pdf.cell(PW, 5, "\u57fa\u4e8e cangjie \u84b8\u998f\u7ed3\u679c | \u6570\u636e\u6e90: How to Implement Lean Manufacturing (Lonnie Wilson, 2010)", new_x="LMARGIN", new_y="NEXT", align="C")
pdf.cell(PW, 5, "Created: 2026-07-12", new_x="LMARGIN", new_y="NEXT", align="C")

out = r"C:\Users\TobyC\hermes_related\Cornell_KB\lean_learning_plan.pdf"
pdf.output(out)
print(f"PDF saved: {out}")
