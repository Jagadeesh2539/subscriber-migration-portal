# Resolve Step Functions ARNs at runtime to avoid CFN circular dependencies
# and to keep auth minimal, we export ARNs as CFN Outputs and let the
# orchestrator discover them using DescribeStacks.

import boto3
import os

_cf = boto3.client('cloudformation')
_cache = {
    'migration': None,
    'audit': None,
    'export': None
}


def get_workflow_arns():
    """Return a dict with workflow ARNs {migration, audit, export}.
    Uses CFN DescribeStacks on the current stack from AWS_STACK_NAME.
    Results cached in module-level _cache.
    """
    global _cache
    if all(_cache.values()):
        return _cache

    stack_name = os.environ.get('AWS_STACK_NAME') or os.environ.get('STACK_NAME')
    if not stack_name:
        # Fallback: try to infer from SAM default StackName env var if present
        stack_name = os.environ.get('AWS_SAM_STACK_NAME', '')

    if not stack_name:
        raise RuntimeError('AWS_STACK_NAME not set')

    resp = _cf.describe_stacks(StackName=stack_name)
    outputs = {o['OutputKey']: o['OutputValue'] for o in resp['Stacks'][0].get('Outputs', [])}

    _cache['migration'] = outputs.get('MigrationWorkflowArn')
    _cache['audit'] = outputs.get('AuditWorkflowArn')
    _cache['export'] = outputs.get('ExportWorkflowArn')

    if not all(_cache.values()):
        raise RuntimeError(f"Missing workflow ARNs in stack outputs for {stack_name}")

    return _cache
