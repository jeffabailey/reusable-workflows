# Reusable GitHub Actions Workflows

This repository contains reusable GitHub Actions workflows for common deployment and automation tasks.

## Available Workflows

### `hugo-deploy.yml`
A comprehensive Hugo deployment workflow that builds and deploys Hugo sites to AWS S3 with CloudFront invalidation.

**Features:**
- Hugo build with caching
- AWS S3 sync with proper ACLs
- CloudFront cache invalidation
- Lighthouse performance auditing
- Automatic cleanup

**Inputs:**
- `website_repository` (required): The repository containing the Hugo site
- `s3_bucket_name` (required): S3 bucket name for deployment
- `cloudfront_distribution_id` (required): CloudFront distribution ID for cache invalidation
- `site_meta_url` (required): Base URL of the site for Lighthouse auditing

**Secrets:**
- `aws_access_key_id` (required): AWS access key for S3 and CloudFront operations
- `aws_secret_access_key` (required): AWS secret key for S3 and CloudFront operations
- `access_token` (required): GitHub token for repository checkout

### `generate-diagrams.yml`
Generates diagrams from Mermaid source files and commits them to the repository.

**Features:**
- Mermaid diagram generation
- Automatic commit of generated images
- Support for multiple diagram formats

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
      site_meta_url: "https://example.com/"
    secrets:
      aws_access_key_id: ${{ secrets.AWS_ACCESS_KEY_ID }}
      aws_secret_access_key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
      access_token: ${{ secrets.ACCESS_TOKEN }}
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
