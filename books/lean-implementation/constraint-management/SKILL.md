---
name: lean-constraint-management
description: "Identify and manage bottlenecks/constraints in manufacturing. Trigger when: user has a bottleneck limiting throughput, asks 'how to improve the bottleneck', or needs to increase capacity."
tags: [lean, constraint, bottleneck, throughput, TOC]
version: 1.0.0
source: "How to Implement Lean Manufacturing — Lonnie Wilson, Ch 12"
---

# Constraint Management (约束管理)

## R — Reading

> "Every process has a constraint. There are constraints to our manufacturing processes, our engineering processes, and constraints to our business process. Every process that has an objective has a constraint, unless the objective is fully met." — Ch 12, p.189

## I — Interpretation

The constraint (bottleneck) is the limiting aspect of a process — usually the step with the longest cycle time. The management cycle:

1. **Identify**: Find the constraint (time study, OEE analysis)
2. **Exploit**: Maximize the constraint's output (never let it idle)
3. **Subordinate**: All other steps serve the constraint
4. **Elevate**: Increase constraint capacity (if needed after exploitation)
5. **Repeat**: Once the constraint moves, start over

**Constraint types:**
- Process step (longest cycle time) — most common
- Moving constraint (from line balancing, variation causes it to shift)
- Sales constraint (market not fully captured)
- Policy constraint (company rules limiting performance)
- Supplier constraint (unreliable materials)

**Key insight**: The constraint is not always a process step. It can be any aspect that limits your ability to meet your objective — including policies.

## A1 — Past Application

The ABC Widgets case (Ch 17) identified a welding machine with low availability as the bottleneck. Addressing this constraint provided the "low-hanging fruit" for early process gains. The author notes that constraint management is often the most powerful tool in the Lean toolbox for quick wins.

## A2 — Future Trigger

- "What's our bottleneck?"
- "How to increase throughput?"
- "One station is slowing everything down"
- "We need more capacity but can't buy equipment"
- "Where should we focus improvement efforts?"

## E — Execution

1. **Do time studies** at every workstation
2. **Identify the constraint** (longest cycle time step)
3. **Measure OEE** at the constraint
4. **Exploit**: Ensure the constraint never idles (no breaks, no changeovers during production, no quality stops)
5. **Subordinate**: Adjust all other steps to feed the constraint at its pace
6. **Evaluate**: Is exploitation enough? If not, elevate
7. **Elevate**: Add capacity at the constraint (overtime, equipment, process improvement)
8. **Monitor**: When the constraint moves, restart the cycle

## B — Boundary

- **NOT for**: Processes already balanced and performing to takt
- **NOT for**: Systems where the constraint is a policy (requires management change)
- **Requires**: Accurate time studies and OEE data
- **Warning**: Line balancing can create moving constraints — don't over-balance
- **Limitation**: Constraint management is a subset of Lean; it doesn't replace the full system
