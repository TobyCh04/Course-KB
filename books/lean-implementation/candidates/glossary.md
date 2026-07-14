# Candidate Glossary — How to Implement Lean Manufacturing

## Core Concepts

### TPS (Toyota Production System) 丰田生产系统
- **Definition**: The manufacturing philosophy developed at Toyota, built on JIT and Jidoka
- **Usage**: Often used interchangeably with Lean Manufacturing, though the author notes TPS is specifically a quantity control system
- **Related**: Lean Manufacturing, JIT, Jidoka, Ohno

### Lean Manufacturing 精益制造
- **Definition**: A production system characterized by using less material, less investment, less inventory, less space, and less people, while maintaining flow and predictability
- **Usage**: The overarching philosophy of this book
- **Related**: TPS, Waste Elimination, Lead Time Reduction

### JIT (Just-In-Time) 准时制
- **Definition**: Produce only what is needed, when it is needed, in the amount needed
- **Usage**: One of the two pillars of TPS; requires takt time, continuous flow, pull system
- **Related**: Takt Time, Pull System, Kanban, Flow

### Jidoka 自动化 (带人字旁)
- **Definition**: Automation with a human touch; machines detect and stop on defects; workers can stop the line
- **Usage**: The second pillar of TPS; distinguishes TPS from simple automation
- **Related**: Andon, Poka Yoke, Problem Solving by All

### Muda 浪费 (无駄)
- **Definition**: Any activity that adds no value; the seven wastes
- **Usage**: The target of Lean elimination efforts
- **Seven wastes**: Transportation, Waiting, Overproduction, Defects, Inventory, Movement, Excess Processing (TWO DIME)
- **Related**: Kaizen, Value Stream Mapping

## Production Control Terms

### Takt Time 节拍时间
- **Definition**: Available production time / customer demand rate; the rate at which products must be produced to meet customer demand
- **Usage**: Sets the pace for all production; foundation of synchronized manufacturing
- **Related**: Cycle Time, Line Balancing, JIT

### Cycle Time 周期时间
- **Definition**: Time to complete one unit of production at a specific workstation
- **Usage**: Compared to takt time to identify bottlenecks and imbalances
- **Related**: Takt Time, Bottleneck, OEE

### Lead Time 交付周期
- **Definition**: Time from order placement to delivery; = Processing time + Waiting time + Move time + Queue time
- **Usage**: The primary Lean metric; typically 95-99% is non-value-added
- **Related**: Little's Law, Value Stream Mapping, Flow

### Kanban 看板
- **Definition**: Visual signal system for pull-based production control; cards or signals that authorize production
- **Usage**: Implements pull system; sized using demand, lead time, and safety factors
- **Related**: Pull System, JIT, Inventory Management

### OEE (Overall Equipment Effectiveness) 设备综合效率
- **Definition**: Measure of equipment performance combining availability, performance rate, and quality rate
- **Usage**: Quantifies process losses; identifies where improvement is needed
- **Related**: TPM, Cycle Time, Bottleneck

## Improvement Terms

### Kaizen 改善
- **Definition**: Continuous improvement through small, incremental changes
- **Usage**: The improvement methodology within Lean; small group activities
- **Related**: CIP, Problem Solving, Waste Elimination

### Poka Yoke 防错
- **Definition**: Error-proofing mechanisms to prevent defects; design features that make it impossible to make mistakes
- **Usage**: Quality control tool; prevents defects rather than detecting them
- **Related**: Jidoka, Quality Control

### SMED (Single-Minute Exchange of Die) 快速换模
- **Definition**: Method to reduce setup/changeover time to under 10 minutes
- **Usage**: Enables smaller lot sizes and more frequent changeovers
- **Related**: Lead Time Reduction, Flexibility, Flow

### TPM (Total Productive Maintenance) 全面生产维护
- **Definition**: Systematic equipment maintenance to prevent breakdowns; operators participate in maintenance
- **Usage**: Foundation of stability in the House of Lean
- **Related**: OEE, Availability, Stability

### 5S
- **Definition**: Workplace organization method: Sort, Set in order, Shine, Standardize, Sustain
- **Usage**: Foundation of Lean; creates visual workplace
- **Related**: Stability, Standard Work, Visual Management

### Value Stream Mapping (VSM) 价值流图
- **Definition**: Visual tool to map material and information flow through a production process
- **Usage**: Shows where time is actually spent; identifies waste; creates future state vision
- **Related**: Lead Time, Waste Identification, Four Strategies

## Organizational Terms

### Standard Work 标准作业
- **Definition**: Documented best known method for performing a task
- **Usage**: Foundation for improvement; must exist before improvement can be sustained
- **Related**: 5S, Sustaining Gains, Training

### Andon 安灯
- **Definition**: Visual signal system (lights/boards) for production status; workers can signal problems
- **Usage**: Enables jidoka; visible management of production flow
- **Related**: Jidoka, Line Shutdown, Problem Escalation

### Genchi Genbutsu 现地现物
- **Definition**: "Go and see" — management must observe the actual workplace to understand problems
- **Usage**: Management principle; decisions based on firsthand observation
- **Related**: Leadership, Problem Solving

### Heijunka 平准化
- **Definition**: Production leveling to smooth out volume and product mix
- **Usage**: Strategy 1 of the Four Strategies; synchronizes supply to customer
- **Related**: Takt Time, Model Mix Leveling, JIT

### Five Whys 五个为什么
- **Definition**: Root cause analysis method — ask "why" five times to get to the root cause
- **Usage**: Problem-solving tool; part of jidoka culture
- **Related**: Problem Solving, Root Cause Analysis

## Metrics Terms

### Little's Law 利特尔法则
- **Definition**: Inventory = Throughput × Lead Time
- **Usage**: Fundamental relationship for understanding inventory and lead time
- **Related**: Lead Time, Inventory, Throughput

### Moving Constraint 移动约束
- **Definition**: When line balancing causes the bottleneck to shift between process steps due to variation
- **Usage**: Identifies process instability; measured by OEE
- **Related**: Bottleneck, Line Balancing, Variation

### Safety Stock 安全库存
- **Definition**: Inventory held to protect against internal supply variations
- **Usage**: Part of Strategy 1 (synchronize supply externally)
- **Related**: Buffer Stock, Cycle Stock, Kanban

### Buffer Stock 缓冲库存
- **Definition**: Inventory held to protect against demand variations
- **Usage**: Part of Strategy 1 (synchronize supply externally)
- **Related**: Safety Stock, Cycle Stock, Kanban

### Cycle Stock 周转库存
- **Definition**: Inventory necessary to assure normal pickup deliveries are in place
- **Usage**: Part of Strategy 1; designed inventory, not waste
- **Related**: Safety Stock, Buffer Stock, Kanban
