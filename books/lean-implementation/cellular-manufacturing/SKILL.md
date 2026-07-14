---
name: lean-cellular-manufacturing
description: "Design and implement cellular manufacturing. Trigger when: user has job-shop layout that needs conversion to cells, asks 'how to design a production cell', or needs to improve flow in manufacturing."
tags: [lean, cellular-manufacturing, layout, flow]
version: 1.0.0
source: "How to Implement Lean Manufacturing — Lonnie Wilson, Ch 13"
---

# Cellular Manufacturing Design (单元化制造设计)

## R — Reading

> "A cell is a combination of people, equipment, and workstations organized in the order of process flow, to manufacture all or part of a production unit." — Ch 13, p.195

## I — Interpretation

Cellular manufacturing organizes machines by product family (not function) into C or U-shaped cells. The key principles:

**Cell characteristics:**
- One-piece or very small lot flow
- Used for a family of products
- Right-sized equipment (not the biggest available)
- C or U shape (incoming/outgoing easily monitored)
- Cross-trained operators for flexibility

**Why cells work:**
- Dramatically reduces lead time (no waiting between functional departments)
- Reduces variation (shorter distances, fewer handoffs)
- Enables one-piece flow
- Reduces space requirements
- Improves quality (immediate feedback)

**Design process:**
1. Group products into families (similar processing requirements)
2. Determine cell layout (C, U, or line)
3. Right-size equipment (don't use oversized machines)
4. Cross-train operators
5. Balance work content to takt time

## A1 — Past Application

The Alpha Line (Ch 14) converted from a long flow line to cellular manufacturing, achieving 63% production rate improvement with virtually no capital expenditures and less manpower. The cell redesign calculations proved the benefit before implementation.

## A2 — Future Trigger

- "Our job shop is inefficient"
- "How to organize machines for better flow?"
- "We need to reduce WIP between stations"
- "What layout is best for our product family?"
- "How to improve throughput without buying new equipment?"

## E — Execution

1. **Group products into families** (similar processing sequences)
2. **Determine takt time** for each family
3. **Time each operation** in the current process
4. **Design cell layout** (C or U shape preferred)
5. **Right-size equipment** (match to cell needs, not maximum capacity)
6. **Balance work content** to takt time
7. **Cross-train operators** (minimum 2 operators per cell for flexibility)
8. **Implement one-piece flow** within the cell
9. **Measure results** (lead time, throughput, quality)

## B — Boundary

- **NOT for**: Extremely high product variety with no family groupings possible
- **NOT for**: Processes requiring massive equipment that can't be right-sized
- **Requires**: Stable processes (standard work must exist)
- **Requires**: Cross-trained workers (cells can't flex without them)
- **Limitation**: Cell design is a quantitative exercise — do the calculations first
