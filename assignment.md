FDE Data Foundations Assignment
Classes 4–8 | From Client Data to a Dependable Pipeline

Assignment objective: Take a realistic operational problem from messy source data to a small, explainable,
dependable data pipeline that produces trustworthy business metrics.

Problem statement
You are the FDE assigned to a client whose operations span multiple systems. Leadership has a business problem, but the
data is fragmented, inconsistent, and not yet organised around the workflow. Your task is to identify the right sources,
retrieve the required data, validate it, model the business workflow, define useful metrics, and build a simple repeatable
pipeline that produces those metrics reliably.
Choose one project track
Track Example problem
A —

FlashEats-
style

Late deliveries are hurting customer experience. Reconstruct the order workflow, identify where delay
accumulates, evaluate operational interventions, and produce a dependable KPI pipeline.

B — NYC TLC Use NYC taxi trip data to build a workflow-oriented view of trips, validate trip-duration/location data,

define 3–5 operational metrics, and automate a repeatable monthly metric pipeline.

C — Your own Choose a real-life operational problem with multiple data sources, e.g. clinic appointments, e-
commerce fulfilment, campus transport, service tickets, logistics, subscriptions, or another domain

you can explain clearly.

What your submission must demonstrate
Class Skill Evidence in your project
4 Understand
sources

Map business questions → required information → source systems. Identify source ownership,
grain, and any important gaps.

5 Retrieve data Use at least two retrieval modes across SQL, API, JSON/CSV/files. Show how you know

retrieval is complete and preserve raw inputs.

6 Profile &
validate

Profile the data, identify meaningful quality issues, define business-oriented validation rules,
and record assumptions/limitations instead of silently fixing them.

7 Model workflow Represent entities, events/states, interactions/interventions/outcomes. Build a simple
relational or event model and calculate 3–5 metrics linked to the project KPI.

8 Dependable
pipeline

Turn the analysis into a repeatable pipeline: ingest → validate → transform/model → metric
output. Include logging/checks, rerun behaviour, and failure handling.

Submission package
• GitHub project URL (required): submit a public or otherwise accessible repository containing the complete project.
• README.md in the repository: problem, users/stakeholders, project KPI, source overview, setup/run instructions, and
what decision the output supports.
• Source map + workflow/data model diagram, stored in the repository (simple is fine).
• Code/notebook(s) showing retrieval, validation, modelling, joins/aggregations, metrics, and a runnable pipeline/script
that reproduces the final output from raw inputs.
• Final evidence table/dashboard with 3–5 metrics, plus a brief Known / Unknown / Assumption / Limitation section.
• A 3–5 minute demo using the GitHub project, explaining one important FDE judgement call you made.
What matters most
We are not grading project size or UI polish. We are looking for evidence that you can move from messy client data to a
trustworthy operational model and a repeatable output. Your choices should be explicit, defensible, and connected to the
business KPI.
Source reasoning Retrieval Validation Workflow + metrics Pipeline dependability
20% 20% 20% 20% 20%
Think like an FDE: the goal is not “I analysed a dataset.” The goal is “I built a trustworthy path from client systems to

a business decision.”