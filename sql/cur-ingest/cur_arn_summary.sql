-- Gold view: cost_by_arn
--
-- Operator-facing view selecting only the columns documented in the
-- data-models.md section 5.1 contract. No aggregation here — operator
-- queries do their own GROUP BY (see README canonical query). Reads
-- resource_arn from cur_typed; never re-applies ARN synthesis rules
-- (ADR-004 single source of truth).
--
-- Templating: __CATALOG__ and __SCHEMA__ are placeholder tokens replaced
-- by terraform at apply time (main.tf templatefile/replace) before the
-- DDL is uploaded as a Databricks notebook.

CREATE OR REPLACE VIEW __CATALOG__.__SCHEMA__.cost_by_arn AS
SELECT
  usage_date,
  resource_arn,
  service,
  unblended_cost,
  usage_amount,
  usage_unit,
  tags
FROM __CATALOG__.__SCHEMA__.cur_typed;
