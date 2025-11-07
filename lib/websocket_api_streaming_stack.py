from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    aws_apigatewayv2 as apigatewayv2,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_cognito as cognito,
    aws_logs as logs,
)
from aws_cdk.aws_lambda_python_alpha import PythonLayerVersion
from aws_cdk.aws_apigatewayv2_integrations import WebSocketLambdaIntegration
from aws_cdk.aws_apigatewayv2_authorizers import WebSocketLambdaAuthorizer
from constructs import Construct
from cdk_nag import NagSuppressions
import os


class WebSocketApiStreamingStack(Stack):
    """
    WebSocket API Streaming Stack

    This stack implements a real-time bidirectional streaming architecture using
    API Gateway WebSocket API for persistent connections. It's ideal for interactive
    LLM applications that need ongoing two-way communication.

    Key Architectural Components:
    1. WebSocket API - For maintaining persistent client connections
    2. Lambda Authorizer - For securing connections with JWT validation
    3. Route Lambdas - Specialized functions for connection lifecycle and streaming
    4. Custom Python Layer - For JWT validation dependencies

    Benefits of this Architecture:
    - Persistent connections for true real-time communication
    - Server-initiated push capabilities (unlike HTTP pull model)
    - Efficient for multiple messages over a single connection
    - Connection-based state tracking for ongoing sessions

    Connection Lifecycle:
    1. Client connects with auth token as query parameter
    2. Lambda authorizer validates the JWT token
    3. Connection is established and connectionId is assigned
    4. Client sends messages through the connection
    5. Server can push messages to client at any time
    6. Connection terminates when either side disconnects
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        user_pool: cognito.UserPool,
        user_pool_client: cognito.UserPoolClient,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a Lambda Layer with the required dependencies
        #
        # Python Lambda Layer Pattern:
        # - Separates dependencies from function code for easier management
        # - Reduces deployment package size for individual functions
        # - Enables sharing common dependencies across multiple functions
        # - Built in a Lambda-like environment to ensure binary compatibility
        # - Contains PyJWT and Cryptography for JWT token validation
        websocket_deps_layer = PythonLayerVersion(
            self,
            "WebSocketDepsLayer",
            entry="lambda_functions/websocket_api",  # Directory containing requirements.txt
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],  # Target runtime
            description="Dependencies for WebSocket API Lambdas (PyJWT, Cryptography)",
        )

        # Define the Lambda code asset
        #
        # Code Organization:
        # - Single code asset for all WebSocket Lambda functions
        # - Each function uses a different entry point (handler)
        # - Enables sharing common utility code across functions
        # - More maintainable than separate code packages
        websocket_api_asset = _lambda.Code.from_asset("lambda_functions/websocket_api")

        # Create IAM role for Lambda functions
        #
        # Shared IAM Role Pattern:
        # - Single role used by all WebSocket Lambda functions
        # - Reduces IAM resource count and simplifies management
        # - Contains all necessary permissions for all functions
        # - Following least privilege with specific actions
        lambda_role = iam.Role(
            self,
            "WebSocketLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            # Standard Lambda execution permissions for logging
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
            inline_policies={
                # Bedrock model access for LLM streaming
                "BedrockInvokePolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                # Streaming-specific permission
                                "bedrock:InvokeModelWithResponseStream",
                                # Regular invoke permission for future use
                                "bedrock:InvokeModel",
                            ],
                            resources=["*"],  # Consider scoping to specific model ARNs
                        )
                    ]
                ),
                # Critical permission for posting messages back to clients
                "ApiGatewayManageConnections": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            # This permission is required to send data back through WebSockets
                            actions=["execute-api:ManageConnections"],
                            # In production, scope this to specific API resources
                            resources=["*"],
                        )
                    ]
                ),
            },
        )

        # Lambda Authorizer function
        #
        # WebSocket Authorization Pattern:
        # - Unlike HTTP APIs where auth headers are used, WebSockets use query parameters
        # - The authorizer function runs on EVERY connection attempt
        # - It validates the JWT token against Cognito user pool
        # - Security is enforced at the connection level, not at each message
        # - This "authorize-once" pattern is more efficient than per-message auth
        # - A denied connection attempt never establishes the WebSocket
        authorizer_function = _lambda.Function(
            self,
            "WebSocketAuthorizer",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="authorizer.lambda_handler",
            code=websocket_api_asset,
            role=lambda_role,
            layers=[websocket_deps_layer],  # Uses layer for JWT validation
            timeout=Duration.seconds(30),  # Auth should complete quickly
            environment={
                # Cognito configuration for token validation
                "USER_POOL_ID": user_pool.user_pool_id,
                "USER_POOL_CLIENT_ID": user_pool_client.user_pool_client_id,
            },
        )

        # Connect Lambda function
        #
        # WebSocket $connect Route Handler:
        # - Triggered when a client establishes a WebSocket connection
        # - Runs AFTER the authorizer has approved the connection
        # - Receives the connectionId that uniquely identifies this client
        # - Can store connection metadata in DynamoDB (connectionId, user info, etc.)
        # - Could initialize session state or perform additional setup
        # - Must return 200 for the connection to be successfully established
        connect_function = _lambda.Function(
            self,
            "ConnectFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="connect.lambda_handler",
            code=websocket_api_asset,
            role=lambda_role,
            layers=[websocket_deps_layer],  # Access to common utilities
        )

        # Disconnect Lambda function
        #
        # WebSocket $disconnect Route Handler:
        # - Triggered automatically when a client disconnects
        # - Also triggered on connection timeout (10 minutes by default)
        # - Receives the connectionId of the terminated connection
        # - Performs cleanup operations (remove connectionId from database)
        # - Ensures no orphaned connection resources remain
        # - Can trigger final actions when a user session ends
        disconnect_function = _lambda.Function(
            self,
            "DisconnectFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="disconnect.lambda_handler",
            code=websocket_api_asset,
            role=lambda_role,
            layers=[websocket_deps_layer],  # Access to common utilities
        )

        # Stream Lambda function
        #
        # Custom "stream" Route Handler:
        # - Handles messages sent to the "stream" route with JSON format:
        #   {"action": "stream", "data": {"prompt": "..."}}
        # - Receives the connectionId, enabling responses to specific client
        # - Invokes Bedrock with streaming response mode
        # - Forwards each token to client as it arrives using PostToConnection API
        # - Uses PostToConnection to send individual token messages back on same socket
        # - Extended timeout (5 mins) allows for longer LLM generation sessions
        # - Maintains connectionId context throughout the streaming process
        stream_function = _lambda.Function(
            self,
            "StreamFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="stream.lambda_handler",
            code=websocket_api_asset,
            role=lambda_role,
            layers=[websocket_deps_layer],
            timeout=Duration.minutes(5),  # Extended timeout for streaming AI responses
            environment={
                # Environment variables could be added here for Bedrock configuration
            },
        )

        # Create WebSocket API
        #
        # WebSocket APIs vs HTTP APIs:
        # WebSocket APIs maintain persistent connections, enabling real-time bidirectional
        # communication. Perfect for streaming applications where the server needs to
        # push data to clients as it becomes available (like AI streaming responses).
        websocket_api = apigatewayv2.WebSocketApi(
            self,
            "LlmStreamingWebSocketApi",
            api_name="llm-streaming-websocket-api",
            description="WebSocket API for streaming LLM responses",
        )

        # Create Lambda authorizer
        #
        # WebSocket Authorization Pattern:
        # Since WebSockets don't support HTTP headers after the initial handshake,
        # authentication tokens are typically passed as query parameters during connection.
        # The authorizer validates the token before allowing the connection to proceed.
        #
        # Identity Source: route.request.querystring.token
        # This means clients connect with: wss://api-id.execute-api.region.amazonaws.com/stage?token=JWT_TOKEN
        authorizer = WebSocketLambdaAuthorizer(
            "LambdaAuthorizer",
            authorizer_function,
            identity_source=["route.request.querystring.token"],
        )

        # Add WebSocket Routes
        #
        # WebSocket API Route Types:
        #
        # 1. $connect: Special route triggered when clients establish a connection
        #    - Requires authorization (auth happens once during connection)
        #    - Used for connection setup and validation
        #    - Connection is rejected if authorizer returns "Deny"
        websocket_api.add_route(
            "$connect",
            integration=WebSocketLambdaIntegration(
                "ConnectIntegration", connect_function
            ),
            authorizer=authorizer,  # Only $connect route needs authorization
        )

        # 2. $disconnect: Special route triggered when clients disconnect
        #    - No authorization needed (connection already established)
        #    - Used for cleanup and logging
        #    - Automatically triggered on connection close
        websocket_api.add_route(
            "$disconnect",
            integration=WebSocketLambdaIntegration(
                "DisconnectIntegration", disconnect_function
            ),
        )

        # 3. Custom Routes: Handle specific actions after connection is established
        #    - "stream": Custom route for AI streaming requests
        #    - No authorization needed (already validated during $connect)
        #    - Clients send messages to this route: {"action": "stream", "data": {...}}
        websocket_api.add_route(
            "stream",
            integration=WebSocketLambdaIntegration(
                "StreamIntegration", stream_function
            ),
        )

        # Deploy the API
        #
        # WebSocket API Deployment Pattern:
        # - WebSocket APIs require explicit stage deployment (different from HTTP APIs)
        # - Multiple stages can be created (dev, test, prod)
        # - Each stage has its own URL and can be independently configured
        # - Auto-deploy ensures changes are automatically pushed to the stage
        # - Production deployments might disable auto-deploy for controlled releases
        stage = apigatewayv2.WebSocketStage(
            self,
            "ProdStage",
            web_socket_api=websocket_api,
            stage_name="prod",  # Stage name appears in the URL path
            auto_deploy=True,  # Automatically deploy API changes
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
                    "reason": "Wildcard permissions are required for Bedrock model access (dynamic ARNs) and API Gateway ManageConnections (connectionId is dynamic)",
                },
            ],
        )

        # Add CDK-Nag suppressions for WebSocket routes that intentionally don't have authorization
        NagSuppressions.add_resource_suppressions(
            websocket_api.node.find_child("$disconnect-Route"),
            [
                {
                    "id": "AwsSolutions-APIG4",
                    "reason": "$disconnect route does not require authorization as the connection is already authenticated and this is triggered automatically on disconnect",
                }
            ],
        )

        NagSuppressions.add_resource_suppressions(
            websocket_api.node.find_child("stream-Route"),
            [
                {
                    "id": "AwsSolutions-APIG4",
                    "reason": "stream route does not require authorization as the connection was already authenticated during $connect. WebSocket authorization is connection-based, not per-message.",
                }
            ],
        )

        # Suppress access logging finding for WebSocket APIs
        NagSuppressions.add_resource_suppressions(
            stage,
            [
                {
                    "id": "AwsSolutions-APIG1",
                    "reason": "WebSocket APIs do not support access logging in the same way as REST APIs. Logging can be enabled at the Lambda function level for monitoring purposes.",
                }
            ],
        )

        # Suppress Lambda runtime findings for Python functions
        for func in [
            authorizer_function,
            connect_function,
            disconnect_function,
            stream_function,
        ]:
            NagSuppressions.add_resource_suppressions(
                func,
                [
                    {
                        "id": "AwsSolutions-L1",
                        "reason": "Python 3.12 is the latest stable Python runtime available in AWS Lambda. Using the current stable version for reliability.",
                    }
                ],
            )

        # Store references for cross-stack usage
        #
        # Resource References:
        # - Makes key resources available to other stacks if needed
        # - Enables modular architecture with cross-stack references
        # - Allows other stacks to build upon this WebSocket infrastructure
        self.websocket_api = websocket_api
        self.stream_function = stream_function
        self.api_stage = stage

        # Output the WebSocket URL
        #
        # WebSocket Connection Pattern:
        # - Clients use standard WebSocket protocol to connect
        # - URL format follows: wss://{api-id}.execute-api.{region}.amazonaws.com/{stage}
        # - Token must be added as query parameter for authorization
        # - Client workflow:
        #   1. Obtain JWT token from Cognito user pool
        #   2. Connect using: wss://url?token=jwt-token
        #   3. After connection, send messages to the "stream" route
        #   4. Receive streaming tokens from the server
        #   5. Close connection when done
        CfnOutput(
            self,
            "WebSocketApiUrl",
            value=f"wss://{websocket_api.api_id}.execute-api.{self.region}.amazonaws.com/prod",
            description="WebSocket API URL for streaming Amazon Bedrock responses (append ?token=JWT_TOKEN for auth)",
        )
