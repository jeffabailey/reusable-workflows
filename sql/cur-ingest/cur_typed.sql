-- Silver view: cur_typed
--
-- Single source of truth for ARN normalization (ADR-004). The CASE
-- expression below is the ONLY place ARN synthesis rules live. Any other
-- consumer (Gold view, README examples, future tag-grouped views) reads
-- cur_typed.resource_arn rather than re-implementing the rules.
--
-- Mapping authority: data-models.md section 4.1.
-- Fixture mirror:    tests/acceptance/aws-cur-databricks-integration/
--                    steps/fixtures/expected_arns.yaml
--
-- Templating: __CATALOG__ and __SCHEMA__ are placeholder tokens replaced
-- by terraform at apply time (main.tf templatefile/replace) before the
-- DDL is uploaded as a Databricks notebook. Plain string substitution —
-- no SQL parser sees the placeholders.

CREATE OR REPLACE VIEW __CATALOG__.__SCHEMA__.cur_typed AS
SELECT
  CAST(line_item_usage_start_date AS TIMESTAMP)        AS usage_start_ts,
  DATE(CAST(line_item_usage_start_date AS TIMESTAMP))  AS usage_date,
  line_item_product_code                               AS service,
  line_item_resource_id                                AS resource_id_raw,
  CASE
    -- EKS: line_item_resource_id is already a full ARN — passthrough.
    WHEN line_item_product_code = 'AmazonEKS' AND line_item_resource_id LIKE 'arn:%'
      THEN line_item_resource_id

    -- S3: synthesize from bare bucket name.
    WHEN line_item_product_code = 'AmazonS3' AND line_item_resource_id IS NOT NULL AND line_item_resource_id <> ''
      THEN concat('arn:aws:s3:::', line_item_resource_id)

    -- CloudFront: synthesize with account_id (no region in CloudFront ARNs).
    WHEN line_item_product_code = 'AmazonCloudFront' AND line_item_resource_id LIKE 'E%'
      THEN concat('arn:aws:cloudfront::', line_item_usage_account_id, ':distribution/', line_item_resource_id)

    -- Route53: hosted-zone id (Z prefix); no region in Route53 ARNs.
    WHEN line_item_product_code = 'AmazonRoute53' AND line_item_resource_id LIKE 'Z%'
      THEN concat('arn:aws:route53:::hostedzone/', line_item_resource_id)

    -- EC2 instances.
    WHEN line_item_product_code = 'AmazonEC2' AND line_item_resource_id LIKE 'i-%'
      THEN concat('arn:aws:ec2:', product.region, ':', line_item_usage_account_id, ':instance/', line_item_resource_id)

    -- EC2 EBS volumes.
    WHEN line_item_product_code = 'AmazonEC2' AND line_item_resource_id LIKE 'vol-%'
      THEN concat('arn:aws:ec2:', product.region, ':', line_item_usage_account_id, ':volume/', line_item_resource_id)

    -- EC2 elastic network interfaces.
    WHEN line_item_product_code = 'AmazonEC2' AND line_item_resource_id LIKE 'eni-%'
      THEN concat('arn:aws:ec2:', product.region, ':', line_item_usage_account_id, ':network-interface/', line_item_resource_id)

    -- EC2 security groups.
    WHEN line_item_product_code = 'AmazonEC2' AND line_item_resource_id LIKE 'sg-%'
      THEN concat('arn:aws:ec2:', product.region, ':', line_item_usage_account_id, ':security-group/', line_item_resource_id)

    -- EC2 EBS snapshots.
    WHEN line_item_product_code = 'AmazonEC2' AND line_item_resource_id LIKE 'snap-%'
      THEN concat('arn:aws:ec2:', product.region, ':', line_item_usage_account_id, ':snapshot/', line_item_resource_id)

    -- Fallthrough: untaggable / unsupported / empty resource_id.
    ELSE NULL
  END                                                  AS resource_arn,
  CAST(line_item_unblended_cost AS DECIMAL(18, 9))     AS unblended_cost,
  CAST(line_item_usage_amount  AS DECIMAL(18, 9))      AS usage_amount,
  pricing_unit                                         AS usage_unit,
  line_item_line_item_type                             AS line_item_type,
  line_item_usage_account_id                           AS account_id,
  product.region                                       AS region,
  resource_tags                                        AS tags,
  BILLING_PERIOD                                       AS billing_period
FROM __CATALOG__.__SCHEMA__.cur_raw;
