---
name: lean-kanban-calculation
description: "Calculate kanban sizes, safety stock, buffer stock, and cycle stock for pull-based production. Trigger when: user needs to set up a kanban system, asks 'how many kanbans do we need', or needs to size inventory for pull production."
tags: [lean, kanban, pull-system, inventory, calculation]
version: 1.0.0
source: "How to Implement Lean Manufacturing — Lonnie Wilson, Ch 3"
---

# Kanban Calculation (看板计算)

## R — Reading

> "Kanban size = (Daily demand × Lead time × Safety factor) / Container size" — Ch 3, simplified formula

## I — Interpretation

Kanban is a visual signal system for pull-based production control. The calculation is quantitative, not intuitive.

**Three types of inventory:**
1. **Cycle Stock (周转库存)**: Necessary to assure normal pickup deliveries
2. **Buffer Stock (缓冲库存)**: Handles demand variations
3. **Safety Stock (安全库存)**: Handles internal supply variations

**Kanban calculation factors:**
- Daily demand (customer rate)
- Lead time (time to replenish)
- Safety factor (accounts for variation)
- Container size (how many units per kanban)

**Make-to-Stock vs Make-to-Order:**
- MTS: Produce ahead of demand, hold finished goods, use kanban
- MTO: Produce after order, minimal inventory, longer lead time
- Decision factors: Demand variability, product variety, lead time requirements

**Little's Law application:**
- Inventory = Throughput × Lead Time
- Use this to diagnose why inventory exists
- Reducing lead time reduces required inventory

## A1 — Past Application

Ch 3 provides detailed examples of kanban calculations for finished goods inventory, including how to account for supply variation (safety stock) and demand variation (buffer stock). The calculations ensure minimum inventory while protecting customer supply.

## A2 — Future Trigger

- "How many kanbans do we need?"
- "What inventory level should we maintain?"
- "How to set up a pull system?"
- "Should we make-to-stock or make-to-order?"
- "How to calculate safety stock?"

## E — Execution

1. **Determine daily demand**: Average customer orders per day
2. **Measure lead time**: Time from signal to replenishment
3. **Calculate cycle stock**: Demand × lead time
4. **Calculate safety stock**: Based on supply variation (typically 2-3 sigma)
5. **Calculate buffer stock**: Based on demand variation
6. **Total inventory**: Cycle + Safety + Buffer
7. **Determine kanban size**: Container size that's practical to handle
8. **Number of kanbans**: Total inventory / kanban size
9. **Implement and monitor**: Track actual vs calculated; adjust as needed

## B — Boundary

- **NOT for**: Processes with highly unpredictable demand (no stable basis for calculation)
- **NOT for**: Make-to-order with long lead times (different approach needed)
- **Requires**: Accurate demand data and lead time measurements
- **Warning**: Kanban sizing is a starting point — adjust based on actual performance
- **Limitation**: The formula is simplified; real implementations may need more sophisticated calculations
