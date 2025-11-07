#!/usr/bin/env python3
import os
import aws_cdk as cdk
from lib.auth_stack import AuthStack
from lib.lambda_url_streaming_stack import LambdaUrlStreamingStack
from lib.websocket_api_streaming_stack import WebSocketApiStreamingStack
from lib.appsync_streaming_stack import AppSyncStreamingStack
from aws_cdk import aws_iam as iam
from cdk_nag import AwsSolutionsChecks, HIPAASecurityChecks, NIST80053R5Checks

app = cdk.App()

# Get AWS account and region from environment or CDK context
env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION")
)

# Shared authentication stack
auth_stack = AuthStack(app, "ServerlessLlmStreamingAuthStack", env=env)

# Option 1: Lambda Function URL with Response Streaming
lambda_url_stack = LambdaUrlStreamingStack(
    app,
    "LambdaUrlStreamingStack",
    user_pool=auth_stack.user_pool,
    user_pool_client=auth_stack.user_pool_client,
    env=env,
)

# Option 2: API Gateway WebSocket API
websocket_stack = WebSocketApiStreamingStack(
    app,
    "WebSocketApiStreamingStack",
    user_pool=auth_stack.user_pool,
    user_pool_client=auth_stack.user_pool_client,
    env=env,
)

# Option 3: AppSync with GraphQL Subscriptions (Real-time streaming with Cognito)
appsync_streaming_stack = AppSyncStreamingStack(
    app,
    "AppSyncStreamingStack",
    user_pool=auth_stack.user_pool,
    user_pool_client=auth_stack.user_pool_client,
    env=env,
)

# Add stack dependencies
lambda_url_stack.add_dependency(auth_stack)
websocket_stack.add_dependency(auth_stack)
appsync_streaming_stack.add_dependency(auth_stack)

# Add cdk-nag checks to all stacks
cdk.Aspects.of(app).add(AwsSolutionsChecks())

app.synth()
