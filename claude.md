# Project Rules

## Core Principles

* business first
* baseline first
* SQL first
* avoid overengineering
* preserve reproducibility

---

## Analysis Rules

* prioritize business interpretation
* explain metric meaning
* focus on conversion and retention
* preserve time ordering in temporal analysis

---

## SQL Rules

* prefer SQL for data cleaning and aggregation
* separate SQL scripts by analysis topic
* avoid hardcoded logic

---

## Python Rules

* use Python for advanced analysis only
* avoid unnecessary ML models
* prioritize interpretability

---

## Visualization Rules

Dashboard should include:

* DAU
* retention
* conversion funnel
* user segmentation

---

## Experiment Rules

* validate statistical significance
* include control and treatment comparison
* explain business impact

---

## Logging

Important findings should be recorded in:

* experiment_log.md
* insight_log.md
* debugging_log.md
