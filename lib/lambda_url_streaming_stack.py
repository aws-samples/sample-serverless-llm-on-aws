from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_cognito as cognito,
)
from constructs import Construct
from cdk_nag import NagSuppressions
import os


class LambdaUrlStreamingStack(Stack):
    """
    Lambda URL Streaming Stack

    This stack implements the simplest of the three streaming architectures using
    Lambda Function URLs with response streaming. This architecture provides a direct,
    single-function approach to streaming LLM responses from Amazon Bedrock.

    Key Architectural Components:
    1. Lambda Function - A single Node.js Lambda function with response streaming enabled
    2. Function URL - HTTP endpoint with CORS configuration for direct client access
    3. Cognito Authentication - JWT validation happens inside the Lambda function

    Benefits of this Architecture:
    - Simplicity: Single function with no additional AWS services needed
    - Low latency: Direct streaming from Lambda to client
    - Cost effectiveness: Minimal AWS resources required
    - Easy to deploy and manage

    Limitations:
    - Requires Node.js runtime (the only runtime with response streaming support)
    - Limited to HTTP streaming (connection-based, not subscription-based)
    - 15-minute maximum execution time (Lambda timeout)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        user_pool: cognito.UserPool,
        user_pool_client: cognito.UserPoolClient,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create IAM role for Lambda function
        #
        # IAM Role for Lambda:
        # - Provides the necessary permissions for the Lambda function
        # - Includes basic execution permissions (logs, etc.)
        # - Adds Bedrock-specific permissions for model invocation
        # - Following principle of least privilege with specific actions
        lambda_role = iam.Role(
            self,
            "LambdaUrlStreamingRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            # Standard Lambda execution role for CloudWatch logs
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
            inline_policies={
                # Custom policy for Bedrock model access
                "BedrockInvokePolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                # Streaming-specific API permission
                                "bedrock:InvokeModelWithResponseStream",
                                # Regular invoke permission (for future flexibility)
                                "bedrock:InvokeModel",
                            ],
                            resources=[
                                "*"
                            ],  # Consider limiting to specific model ARNs in production
                        )
                    ]
                )
            },
        )

        # Create Lambda function for streaming responses
        #
        # Response Streaming Lambda:
        # - Uses Node.js runtime, which is required for Lambda response streaming
        # - Configured with a longer timeout (5 minutes) for extended streaming sessions
        # - Handles token validation, prompt processing, and streaming in a single function
        # - Environment variables allow the function to validate Cognito tokens
        streaming_function = _lambda.Function(
            self,
            "StreamingFunction",
            runtime=_lambda.Runtime.NODEJS_22_X,
            handler="index.handler",
            code=_lambda.Code.from_asset("lambda_functions/lambda_url_streaming"),
            role=lambda_role,
            timeout=Duration.minutes(5),  # Extended timeout for longer conversations
            environment={
                # Cognito user pool details for JWT token validation
                "USER_POOL_ID": user_pool.user_pool_id,
                "USER_POOL_CLIENT_ID": user_pool_client.user_pool_client_id,
            },
        )

        # Add CDK-Nag suppressions for acceptable findings
        NagSuppressions.add_resource_suppressions(
            lambda_role,
            [
                {
                    "id": "AwsSolutions-IAM4",
                    "reason": "AWSLambdaBasicExecutionRole is the standard managed policy for Lambda execution roles and provides necessary CloudWatch Logs permissions",
                },
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Bedrock model access requires wildcard permissions as model ARNs are dynamic and region-specific. This is the standard pattern for Bedrock access.",
                },
            ],
        )

        # Create Function URL with proper CORS configuration
        #
        # Lambda Function URL Pattern:
        # - Provides a dedicated HTTP(S) endpoint for the Lambda function
        # - No API Gateway needed, reducing complexity and cost
        # - RESPONSE_STREAM invoke mode is critical for enabling HTTP streaming
        # - CORS configuration enables browser clients to access the endpoint
        # - Authentication handled via JWT tokens inside the function, not at URL level
        function_url = streaming_function.add_function_url(
            # No authorization at the URL level; handled by the function itself
            auth_type=_lambda.FunctionUrlAuthType.NONE,
            # This is the key setting that enables HTTP response streaming
            invoke_mode=_lambda.InvokeMode.RESPONSE_STREAM,
            # CORS configuration for web browser access
            cors=_lambda.FunctionUrlCorsOptions(
                allowed_origins=["*"],  # Allow all origins for development
                allowed_methods=[_lambda.HttpMethod.POST],  # Only POST method needed
                allowed_headers=["Content-Type", "Authorization"],  # Required headers
                allow_credentials=False,  # Must be False when using * for origins
                max_age=Duration.seconds(
                    86400
                ),  # Cache preflight response for 24 hours
            ),
        )

        # Output the Function URL
        #
        # CloudFormation Output:
        # - Makes the Function URL available in the AWS Console
        # - Enables easy access and testing of the streaming endpoint
        # - The URL has format: https://<id>.lambda-url.<region>.on.aws/
        CfnOutput(
            self,
            "StreamingFunctionUrl",
            value=function_url.url,
            description="Lambda Function URL for streaming Amazon Bedrock responses",
        )
