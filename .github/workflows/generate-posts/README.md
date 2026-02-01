# Export posts for Databricks

Exports all Hugo pages, blog posts, and prompts into a Databricks-friendly format (JSON Lines) and uploads to S3.

## How it works

- **Source of truth:** The workflow runs `hugo list all` and uses only that CSV output. No custom parsing of content files, so the export stays compatible with Hugo’s data model.
- **Script:** `export_posts.py` reads the CSV (stdlib only, no extra packages), adds derived fields (`content_type`, `export_timestamp`), and writes one JSON object per line (`.jsonl`).
- **S3:** The workflow uploads `posts_export.jsonl` to the configured bucket.

## Metadata in the export

Each record includes the columns from `hugo list all`:

- `path`, `slug`, `title`, `date`, `expiryDate`, `publishDate`, `draft`, `permalink`, `kind`, `section`

Plus derived fields:

- `content_type`: `blog` | `page` | `prompt` | `other` (from path)
- `export_timestamp`: ISO 8601 UTC time of the export

## Running the workflow

This workflow is **reusable** (`workflow_call`). The repo that owns the Hugo site should:

1. Call it from a local workflow (see example below).
2. For **on-demand** runs: use `workflow_dispatch`.
3. For **every 24 hours**: add `schedule: cron('0 0 * * *')` (midnight UTC daily).

### Example caller (e.g. in your blog repo)

```yaml
name: Export posts for Databricks

on:
  workflow_dispatch: {}
  schedule:
    - cron: '0 0 * * *'   # every day at midnight UTC

jobs:
  export:
    uses: jeffabailey/reusable-workflows/.github/workflows/generate-posts.yml@master
    with:
      website_repository: your-org/your-blog-repo
      debug: false
    secrets:
      access_token: ${{ secrets.ACCESS_TOKEN }}
      aws_access_key_id: ${{ secrets.AWS_ACCESS_KEY_ID }}
      aws_secret_access_key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
      aws_s3_bucket: ${{ secrets.AWS_S3_BUCKET }}
```

Replace `your-org/your-blog-repo` and the secret names with your values.

## Databricks import

Use the uploaded `posts_export.jsonl` in S3 as a JSON Lines source. In Databricks you can read it with Spark or SQL (e.g. `COPY INTO` or `spark.read.json(...)`).
