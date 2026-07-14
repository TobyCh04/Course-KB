---
name: lean-lead-time-analysis
description: "Analyze and reduce lead time using the seven techniques. Trigger when: user has long delivery times, asks 'how to reduce lead time', or needs to improve responsiveness/flexibility."
tags: [lean, lead-time, metrics, improvement]
version: 1.0.0
source: "How to Implement Lean Manufacturing — Lonnie Wilson, Ch 5"
---

# Lead Time Analysis (交付周期分析)

## R — Reading

> "All we are doing is looking at the time line, from the moment the customer gives us an order to the point when we collect the cash… And we are reducing that time line by removing the non-value-added wastes." — Ohno, Ch 5, p.74

## I — Interpretation

Lead time is THE primary metric of Lean. The decomposition:

**Lead Time = Processing Time + Waiting Time + Move Time + Queue Time**

Typically 95-99% of lead time is non-value-added. The key insight: reduce lead time and everything else improves (cost, quality, flexibility, responsiveness).

**Seven techniques to reduce lead time:**
1. Reduce setup/changeover times (SMED)
2. Reduce lot sizes
3. Reduce work-in-process
4. Improve equipment reliability (TPM)
5. Improve quality yields
6. Level the production schedule (heijunka)
7. Improve layout (reduce move times)

**Business benefits**: Better cash flow, manufacturing flexibility, responsiveness to customer changes, competitive advantage.

## A1 — Past Application

The Bravo Line (Ch 15) demonstrated how lead time reduction enabled faster plan changes and better delivery performance. Ohno at Toyota used lead time as the primary improvement metric, focusing on the timeline from order to cash collection.

## A2 — Future Trigger

- "Our delivery times are too long"
- "How to improve manufacturing responsiveness?"
- "What should we measure to track Lean progress?"
- "We need to reduce WIP inventory"
- "Customer is complaining about late deliveries"

## E — Execution

1. **Map the current state**: Value stream map showing total lead time
2. **Decompose lead time**: Break into processing, waiting, move, queue components
3. **Identify the biggest waste**: Usually waiting/queue time (95-99% of total)
4. **Apply the 7 techniques** in order of impact:
   - SMED for setup time reduction
   - Reduce lot sizes (enables smaller batches)
   - Reduce WIP (exposes problems, reduces queue time)
   - TPM for equipment reliability
   - Quality improvement (reduces rework delays)
   - Level the schedule (reduces demand spikes)
   - Improve layout (reduces move time)
5. **Measure new lead time**: Compare to baseline
6. **Repeat**: Lead time reduction is continuous

## B — Boundary

- **NOT for**: Processes where the constraint is outside manufacturing
- **NOT for**: Systems that aren't stable yet (stabilize first)
- **Limitation**: Lead time reduction requires addressing ALL seven techniques, not just one
- **Warning**: Reducing inventory without solving underlying problems will cause stockouts
