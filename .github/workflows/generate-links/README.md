# Generate Markdown Links Workflow

This workflow uses GitHub Copilot CLI to automatically generate and add internal links to markdown files in your repository.

## Local Usage

You can run the link generation script locally from any Hugo website directory:

```bash
# From your Hugo site directory
cd /path/to/your/hugo/site

# Run the script (adjust path as needed)
~/Projects/canzan/reusable-workflows/.github/workflows/generate-links/generate-links.sh

# Or generate links for a single file (path relative to cwd or content folder)
~/Projects/canzan/reusable-workflows/.github/workflows/generate-links/generate-links.sh content/blog/my-post/index.md
```

Or set it as an alias in your shell:

```bash
alias generate-links='~/Projects/canzan/reusable-workflows/.github/workflows/generate-links/generate-links.sh'
```

The script will:
1. Check prerequisites (Hugo, Python, Copilot CLI)
2. Read your prompt file (default: `content/prompts/internal-link-optimize.md`)
3. Generate Hugo list of published posts
4. Run the Python script to generate links

### Environment Variables

You can customize the script behavior with environment variables:

- `CONTENT_FOLDER`: Path to content folder (default: `content/blog`)
- `PROMPT_FILE`: Path to prompt file (default: `content/prompts/internal-link-optimize.md`)
- `CUSTOM_PROMPT`: Custom prompt text (overrides prompt file)
- `COPILOT_GITHUB_TOKEN`: GitHub token with Copilot API access (required)
- `TARGET_FILE`: Path to a specific file to generate links for (optional; can also pass as first positional argument)
- `DEBUG`: Enable debug output (`true`/`false`)
- `DRY_RUN`: Preview changes without modifying files (`true`/`false`)
- `REUSABLE_WORKFLOWS_DIR`: Path to reusable-workflows directory (if not in default location)

## Prerequisites

Before using this workflow, ensure you have:

1. **GitHub Copilot Subscription**: An active GitHub Copilot subscription (individual or organization)
2. **Node.js v22+**: Required for installing the Copilot CLI (the workflow handles this automatically)
3. **Python 3.11+**: Required for running the script (the workflow handles this automatically)

## Setup Instructions

### Step 1: Create a Personal Access Token

You need to create a Personal Access Token (PAT) to authenticate the Copilot CLI in GitHub Actions.

**Important Note**: Fine-grained tokens may not work reliably with Copilot CLI due to known issues. If you encounter authentication errors, use a Classic token instead (see Option B below).

#### Option A: Fine-Grained Personal Access Token (May Not Work)

1. **Navigate to GitHub Settings**:
   - Go to [GitHub Settings](https://github.com/settings/profile)
   - Click on **Developer settings** in the left sidebar
   - Click on **Personal access tokens** → **Fine-grained tokens**

2. **Generate a New Token**:
   - Click **Generate new token**
   - Give your token a descriptive name (e.g., "Copilot CLI for GitHub Actions")
   - Set an expiration date (recommended: 90 days or custom based on your security policy)
   - Select the repository or organization where you'll use this token

3. **Configure Token Permissions**:
   - Under **Repository permissions**, find the **Copilot** section
   - Enable the following Copilot permissions:
     - **Copilot Chat**: Required to send messages to Copilot Chat API
     - **Copilot Requests**: Required to send Copilot requests
     - **Copilot Editor Context** (optional): Provides editor context when sending messages
   - You may also need **Contents: Read and write** if the workflow needs to commit changes

4. **Generate and Copy the Token**:
   - Click **Generate token** at the bottom
   - **Important**: Copy the token immediately - you won't be able to see it again!
   - Store it securely until you add it to GitHub Secrets

#### Option B: Classic Personal Access Token (Recommended)

If fine-grained tokens don't work, use a Classic token:

1. **Navigate to GitHub Settings**:
   - Go to [GitHub Settings](https://github.com/settings/profile)
   - Click on **Developer settings** in the left sidebar
   - Click on **Personal access tokens** → **Tokens (classic)**

2. **Generate a New Token**:
   - Click **Generate new token (classic)**
   - Give your token a descriptive name (e.g., "Copilot CLI for GitHub Actions")
   - Set an expiration date (recommended: 90 days or custom based on your security policy)
   - Select the following scopes:
     - **`repo`**: Full control of private repositories (required for repository access)
     - **`copilot`**: Access to GitHub Copilot API (if available as a scope)
     - Note: If `copilot` scope is not available, the `repo` scope may be sufficient

3. **Generate and Copy the Token**:
   - Click **Generate token** at the bottom
   - **Important**: Copy the token immediately - you won't be able to see it again!
   - Store it securely until you add it to GitHub Secrets

### Step 2: Add Token as GitHub Secret

1. **Navigate to Repository Settings**:
   - Go to your repository on GitHub
   - Click **Settings** → **Secrets and variables** → **Actions**

2. **Add the Secret**:
   - Click **New repository secret**
   - Name: `copilot_token` (must match exactly)
   - Value: Paste the token you copied in Step 1
   - Click **Add secret**

### Step 3: Configure Workflow Inputs

When calling this reusable workflow, you need to pass the `copilot_token` secret:

```yaml
jobs:
  generate-links:
    uses: jeffabailey/reusable-workflows/.github/workflows/generate-links.yml@master
    with:
      website_repository: your-org/your-repo
      content_folder: 'hugo/content/blog'
      prompt_file: '.cursor/seo_optimize.md'
    secrets:
      access_token: ${{ secrets.ACCESS_TOKEN }}
      copilot_token: ${{ secrets.copilot_token }}  # Your Copilot PAT
```

## How It Works

1. **Installation**: The workflow automatically installs the GitHub Copilot CLI via npm if not already available
2. **Authentication**: The workflow uses your `copilot_token` secret to authenticate with the Copilot API
3. **Processing**: The Python script processes markdown files in the specified content folder
4. **Link Generation**: Copilot analyzes each file and adds relevant internal links based on the provided prompt
5. **Commit**: Changes are automatically committed and pushed (if the branch allows)

## Token Requirements

The token must have:
- **Repository access**: Must have access to the repository where the workflow runs
- **Valid expiration**: Ensure the token hasn't expired
- **For Classic tokens**: `repo` scope (full control of private repositories)
- **For Fine-grained tokens**: **Copilot Chat** and **Copilot Requests** permissions (note: may not work due to known issues)

**Recommendation**: Use a Classic Personal Access Token with `repo` scope, as Fine-grained tokens have reported compatibility issues with Copilot CLI.

## Troubleshooting

### Authentication Errors

If you see errors like:
```
copilot CLI error: Error: No authentication information found.
```

**Solutions**:
1. **Try a Classic Token**: Fine-grained tokens may not work with Copilot CLI. Create a Classic Personal Access Token instead (see Step 1, Option B above)
2. Verify the secret is named exactly `copilot_token` (case-sensitive)
3. Check that the token hasn't expired
4. Ensure the token has the `repo` scope (for Classic tokens) or Copilot permissions (for Fine-grained tokens)
5. Verify the token has access to the repository
6. Ensure the token is being passed correctly in the workflow secrets

### Copilot CLI Not Found

If the workflow fails to install Copilot CLI:
- The workflow requires Node.js v22+ (automatically set up)
- Ensure npm is available in the GitHub Actions runner
- Check that your GitHub Copilot subscription is active

### Token Permissions

If you get permission errors:
- **Try a Classic Token**: Fine-grained tokens have known compatibility issues with Copilot CLI. Use a Classic token with `repo` scope instead
- For Fine-grained tokens: Ensure **Copilot Chat** and **Copilot Requests** permissions are enabled
- For Classic tokens: Ensure the `repo` scope is enabled
- Ensure the token has access to the specific repository
- For organization accounts, verify Copilot is enabled for the organization

## Security Best Practices

1. **Token Expiration**: Set a reasonable expiration date and rotate tokens regularly
2. **Minimal Permissions**: Only grant the minimum permissions needed (Copilot + Contents if committing)
3. **Repository Scope**: Limit token access to only the repositories that need it
4. **Secret Management**: Never commit tokens to your repository - always use GitHub Secrets
5. **Monitor Usage**: Regularly review token usage in GitHub Settings → Developer settings → Personal access tokens

## Alternative: Using GITHUB_TOKEN

The workflow can also use the automatically provided `GITHUB_TOKEN`, but this requires:
- Copilot permissions enabled in your repository's workflow settings
- May have limitations compared to a Personal Access Token

**Note**: Due to known issues with Fine-Grained tokens and Copilot CLI, a Classic Personal Access Token with `repo` scope is recommended over using `GITHUB_TOKEN` or Fine-Grained tokens.

## Additional Resources

- [GitHub Copilot Documentation](https://docs.github.com/en/copilot)
- [Fine-Grained Personal Access Tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token#creating-a-fine-grained-personal-access-token)
- [GitHub Actions Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
