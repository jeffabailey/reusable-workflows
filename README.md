# Reusable GitHub Actions Workflows

This repository contains reusable GitHub Actions workflows for common deployment and automation tasks.

## Available Workflows

### `terraform-cost-validate.yml`
A reusable Terraform CI pipeline that runs `fmt`, `validate`, `tflint`, and a full `plan` (AWS + Databricks providers). Designed for modules using:
- AWS provider with profile-based auth (the workflow writes `~/.aws/credentials` with the STS-derived account ID as the profile name).
- S3 state backend with `use_lockfile = true` (Terraform >= 1.10).
- Optional Databricks provider (auths via `DATABRICKS_HOST` + `DATABRICKS_TOKEN` env vars).

**Features:**
- `terraform fmt -check -recursive`, `terraform validate`, `tflint --recursive`.
- `terraform plan` (no `-target` filter); full pipeline including Databricks-side resources.
- Per-account state-key derivation: state lives at `<state_backend_key_prefix>/<aws_account_id>/terraform.tfstate`, so any account whose secrets are configured in the caller is automatically supported.
- PR comment with truncated plan output and a downloadable plan-binary artifact.
- Plan job is gated by a GitHub Environment (default name `plan`); set `plan_environment: ""` to skip the gate.

**Inputs:**
- `working_directory` (required): directory containing the Terraform configuration (e.g. `infrastructure/cost`).
- `state_backend_bucket` (required): S3 bucket holding the Terraform state.
- `state_backend_key_prefix` (required): per-feature key prefix without trailing slash (e.g. `feature/aws-cur-databricks-integration`). The workflow appends `<account_id>/terraform.tfstate`.
- `terraform_version` (optional, default `1.10.3`).
- `tflint_version` (optional, default `v0.53.0`).
- `aws_region` (optional, default `us-east-1`): AWS workload region (not the state-backend region).
- `plan_environment` (optional, default `plan`): GitHub Environment name to gate the plan job on; set to `""` to skip.

**Secrets:**
- `aws_access_key_id` (required).
- `aws_secret_access_key` (required).
- `databricks_host` (required): Databricks workspace URL.
- `databricks_token` (required): personal access token for the workspace.
- `alert_email` (required): used as `TF_VAR_alert_email`.

**Status check naming for branch protection:** the caller's job id prefixes the reusable's job names. With a caller job named `ci`, branch protection should require `ci / validate` and `ci / plan`.

**Caller example:**
```yaml
name: Terraform Cost Feature CI
on:
  pull_request: { branches: [main], paths: ['infrastructure/cost/**'] }
  push:         { branches: [main], paths: ['infrastructure/cost/**'] }
  workflow_dispatch: {}
permissions:
  contents: read
  pull-requests: write
jobs:
  ci:
    uses: jeffabailey/reusable-workflows/.github/workflows/terraform-cost-validate.yml@master
    with:
      working_directory: infrastructure/cost
      state_backend_bucket: jeffbaileyterraformstate
      state_backend_key_prefix: feature/aws-cur-databricks-integration
    secrets:
      aws_access_key_id:     ${{ secrets.AWS_ACCESS_KEY_ID }}
      aws_secret_access_key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
      databricks_host:       ${{ secrets.DATABRICKS_HOST }}
      databricks_token:      ${{ secrets.DATABRICKS_TOKEN }}
      alert_email:           ${{ secrets.ALERT_EMAIL }}
```

### `hugo-deploy.yml`
A comprehensive Hugo deployment workflow that builds and deploys Hugo sites to AWS S3 with CloudFront invalidation.

**Features:**
- Hugo build with caching
- AWS S3 sync with proper ACLs
- CloudFront cache invalidation
- Automatic cleanup

**Inputs:**
- `website_repository` (required): The repository containing the Hugo site
- `s3_bucket_name` (required): S3 bucket name for deployment
- `cloudfront_distribution_id` (required): CloudFront distribution ID for cache invalidation
- `debug` (optional): Enable debug mode for verbose output (default: false)

**Secrets:**
- `aws_access_key_id` (required): AWS access key for S3 and CloudFront operations
- `aws_secret_access_key` (required): AWS secret key for S3 and CloudFront operations
- `access_token` (required): GitHub token for repository checkout

### `lighthouse-audit.yml`
A reusable workflow for running Lighthouse performance audits on websites. Designed to be run on a schedule or manually, separate from deployment workflows.

**Features:**
- Lighthouse CI performance auditing
- Performance budget testing
- Artifact uploads
- Temporary public storage for reports

**Inputs:**
- `site_meta_url` (required): Base URL of the site to audit
- `budget_path` (optional): Path to budget.json file (default: "./budget.json")
- `upload_artifacts` (optional): Upload results as artifacts (default: true)
- `temporary_public_storage` (optional): Upload report to temporary public storage (default: true)

**Secrets:**
- None required

### `generate-diagrams.yml`
Generates diagrams from Mermaid source files and commits them to the repository.

**Features:**
- Mermaid diagram generation
- Automatic commit of generated images
- Support for multiple diagram formats

### `generate-links.yml`
Generates markdown links using GitHub Copilot Chat API. Processes markdown files in a specified directory and adds internal links based on a customizable prompt.

**Features:**
- Uses GitHub Copilot Chat to analyze and enhance markdown files
- Customizable prompts (defaults to SEO optimization prompt)
- Automatic commit of generated links
- Supports processing specific content folders

**Inputs:**
- `website_repository` (required): The repository containing the markdown files
- `content_folder` (optional): Folder to process (default: "content/blog")
- `prompt_file` (optional): Path to prompt file (default: ".cursor/seo_optimize.md")
- `custom_prompt` (optional): Custom prompt text to override the default prompt file
- `debug` (optional): Enable debug mode for verbose output (default: false)

**Secrets:**
- `access_token` (required): GitHub token for repository checkout
- `github_token` (required): GitHub token with Copilot API access

**Requirements:**
- GitHub Copilot subscription
- GitHub CLI (gh) v2.40.0+ with Copilot Chat feature
- Appropriate API permissions for Copilot Chat

## Usage Examples

### Hugo Deployment
```yaml
name: Deploy Website
on:
  push:
    branches: [main]
jobs:
  deploy:
    uses: jeffabailey/reusable-workflows/.github/workflows/hugo-deploy.yml@master
    with:
      website_repository: owner/repo-name
      s3_bucket_name: "my-bucket"
      cloudfront_distribution_id: "E1234567890ABC"
    secrets:
      aws_access_key_id: ${{ secrets.AWS_ACCESS_KEY_ID }}
      aws_secret_access_key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
      access_token: ${{ secrets.ACCESS_TOKEN }}
```

### Lighthouse Audit (Scheduled)
```yaml
name: Lighthouse Audit
on:
  schedule:
    # Run daily at 2 AM UTC
    - cron: '0 2 * * *'
  workflow_dispatch: # Allow manual triggering

jobs:
  lighthouse:
    uses: jeffabailey/reusable-workflows/.github/workflows/lighthouse-audit.yml@master
    with:
      site_meta_url: "https://jeffbailey.us"
      budget_path: "./budget.json" # Optional
```

### Generate Markdown Links
```yaml
name: Generate Markdown Links
on:
  workflow_dispatch:
    inputs:
      content_folder:
        description: 'Content folder to process'
        required: false
        default: 'hugo/content/blog'
        type: string
      custom_prompt:
        description: 'Custom prompt (optional)'
        required: false
        type: string

jobs:
  generate-links:
    uses: jeffabailey/reusable-workflows/.github/workflows/generate-links.yml@master
    with:
      website_repository: owner/repo-name
      content_folder: ${{ inputs.content_folder || 'hugo/content/blog' }}
      prompt_file: '.cursor/seo_optimize.md'
      custom_prompt: ${{ inputs.custom_prompt || '' }}
      debug: true
    secrets:
      access_token: ${{ secrets.ACCESS_TOKEN }}
      github_token: ${{ secrets.GITHUB_TOKEN }}
```

## Testing and Validation

### Local Testing
```bash
# Install act for local testing
brew install act

# Test workflows locally
act -n --workflows .github/workflows/hugo-deploy.yml
```

### Secret Validation
Before using these workflows, ensure all required secrets are defined in your repository settings:

- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key
- `ACCESS_TOKEN`: GitHub personal access token

### Workflow Dependencies
These workflows use the following actions:
- `aws-actions/configure-aws-credentials@v4`
- `actions/checkout@v4`
- `actions/cache@v3`
- `peaceiris/actions-hugo@v2.6.0`
- `treosh/lighthouse-ci-action@v12`
- `rtCamp/action-cleanup@master`

## Maintenance

### Updating Workflows
When updating these workflows:
1. Test changes locally with `act`
2. Update version tags if making breaking changes
3. Update documentation for any new inputs or secrets
4. Test with dependent repositories

### Version Management
- Use semantic versioning for workflow tags
- Maintain backward compatibility when possible
- Document breaking changes in release notes

## Contributing

When contributing to these workflows:
1. Test changes thoroughly with `act`
2. Update documentation for any new features
3. Ensure all required secrets are documented
4. Follow GitHub Actions best practices

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Reusable Workflows](https://docs.github.com/en/actions/using-workflows/reusing-workflows)
- [Act - Local GitHub Actions Runner](https://github.com/nektos/act)
- [Hugo GitHub Action](https://github.com/peaceiris/actions-hugo)
- [AWS Actions](https://github.com/aws-actions)
