# Fix for AWS Bedrock Credential Key Mismatch

## Problem
`GatewayProvider.get_llm()` reads Bedrock credentials using boto3-style key names (`aws_access_key_id`, `aws_secret_access_key`, `region_name`), but the Admin UI stores them via `llm_provider_configs.AWSBedrockConfig` which uses shorter key names (`access_key_id`, `secret_access_key`, `region`).

This mismatch causes `config.get("aws_access_key_id")` to always return `None`, silently falling back to the node IAM role instead of using the user-configured credentials.

## Solution
Update the credential lookup logic in `GatewayProvider.get_llm()` to try both key naming conventions:

```python
# Before (only boto3-style keys)
access_key_id = config.get("aws_access_key_id")
secret_access_key = config.get("aws_secret_access_key")
region_name = config.get("region_name")

# After (fallback to shorter Admin UI keys)
access_key_id = config.get("aws_access_key_id") or config.get("access_key_id")
secret_access_key = config.get("aws_secret_access_key") or config.get("secret_access_key")
region_name = config.get("region_name") or config.get("region")
```

## Implementation Steps
1. Locate `GatewayProvider.get_llm()` method
2. Find the credential retrieval section
3. Update each credential lookup to use fallback logic
4. Test with both key naming conventions

## Verification
- [ ] Config with boto3-style keys works
- [ ] Config with Admin UI-style keys works
- [ ] Fallback behavior is correct
- [ ] No regression in existing functionality