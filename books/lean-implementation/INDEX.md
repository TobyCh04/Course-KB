# INDEX — How to Implement Lean Manufacturing Skills

## Skills Overview

| # | Skill | English | Chinese | Core Concept |
|---|-------|---------|---------|--------------|
| 1 | four-strategies | Four Strategies to Becoming Lean | 精益四策略 | Sync external → Sync internal → Flow → Pull |
| 2 | lean-project-prescription | Eight-Step Lean Project Prescription | 精益项目处方 | Systemwide eval → Value stream eval → Implement → Repeat |
| 3 | lead-time-analysis | Lead Time Analysis | 交付周期分析 | LT = Processing + Waiting + Move + Queue; 95-99% non-VA |
| 4 | cellular-manufacturing | Cellular Manufacturing Design | 单元化制造设计 | Product family cells, one-piece flow, right-sized equipment |
| 5 | constraint-management | Constraint Management | 约束管理 | Identify → Exploit → Subordinate → Elevate → Repeat |
| 6 | house-of-lean | House of Lean | 精益屋 | Roof: Objectives; Pillars: JIT + Jidoka; Foundation: Stability + People |
| 7 | cultural-change | Cultural Change Fundamentals | 文化变革基础 | Leadership + Motivation + Problem Solving before tools |
| 8 | sustaining-gains | Sustaining the Gains | 巩固成果 | Maintenance + Standardization; fix it right, fix it once |
| 9 | kanban-calculation | Kanban Calculation | 看板计算 | Kanban size = (Demand × LT × Safety) / Container |

## Skill Reference Graph

```
                    house-of-lean (overview)
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    cultural-change  four-strategies  lead-time-analysis
         │               │               │
         │         ┌─────┼─────┐         │
         │         │     │     │         │
    sustaining-  kanban-  cellular-  constraint-
    gains        calc     mfg        mfg
         │         │     │         │
         └─────────┴─────┴─────────┘
                   │
            lean-project-prescription
```

## Dependency Notes

- **cultural-change** must come BEFORE **four-strategies** (culture before tools)
- **four-strategies** uses **lead-time-analysis** as the primary metric
- **kanban-calculation** is the quantitative tool for Strategy 4 (Pull)
- **cellular-manufacturing** is the layout tool for Strategy 3 (Flow)
- **constraint-management** identifies where to focus improvement efforts
- **sustaining-gains** ensures improvements from all other skills persist
- **house-of-lean** is the communication/teaching framework that shows how everything fits
- **lean-project-prescription** is the implementation methodology that sequences everything

## Source Chapters

| Chapter | Title | Skills Derived |
|---------|-------|----------------|
| Ch 2 | Lean and TPS | house-of-lean, cultural-change |
| Ch 3 | Inventory and Variation | kanban-calculation |
| Ch 4 | Lean Simplified | house-of-lean |
| Ch 5 | Lead Time | lead-time-analysis |
| Ch 6 | Cultural Change | cultural-change |
| Ch 7 | Four Strategies | four-strategies |
| Ch 8 | Prescription | lean-project-prescription |
| Ch 10 | Sustaining Gains | sustaining-gains |
| Ch 12 | Constraint Mgmt | constraint-management |
| Ch 13 | Cellular Mfg | cellular-manufacturing |
| Ch 20 | House of Lean | house-of-lean |
