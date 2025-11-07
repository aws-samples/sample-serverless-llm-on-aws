from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_appsync as appsync,
    aws_iam as iam,
    aws_logs as logs,
    aws_cognito as cognito,
    Duration,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_sqs as sqs,
    aws_lambda_event_sources as lambda_event_sources,
)
from constructs import Construct
from cdk_nag import NagSuppressions


class AppSyncStreamingStack(Stack):
    """
    AppSync GraphQL API Streaming Stack

    This stack implements a scalable real-time streaming architecture for LLM responses
    using AWS AppSync GraphQL API, SQS messaging, and Lambda functions. It demonstrates
    a message-based pattern for handling long-running operations in a serverless environment.

    Key Architectural Components:
    1. AppSync GraphQL API - For client communications using subscriptions
    2. SQS Queue - For decoupling request and processing functions
    3. Request Lambda - Initial handler for client requests
    4. Processing Lambda - SQS-triggered function for LLM streaming
    5. DynamoDB (optional) - For session tracking

    The architecture follows serverless best practices by avoiding Lambda-to-Lambda
    direct invocation, instead using SQS for message passing between components.
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

        # Create AppSync API with Cognito User Pool and IAM authentication
        #
        # AppSync GraphQL API:
        # - Provides a managed GraphQL service with real-time capabilities
        # - Supports multiple authorization modes (Cognito + IAM in this case)
        # - Enables real-time data through subscriptions
        # - Schema is defined in the external schema.graphql file
        api = appsync.GraphqlApi(
            self,
            "StreamingAPI",
            name="bedrock-streaming-api",
            definition=appsync.Definition.from_file("lib/schema.graphql"),
            authorization_config=appsync.AuthorizationConfig(
                # User Pool auth for client applications
                default_authorization=appsync.AuthorizationMode(
                    authorization_type=appsync.AuthorizationType.USER_POOL,
                    user_pool_config=appsync.UserPoolConfig(user_pool=user_pool),
                ),
                # IAM auth for server-to-server communication (Lambda to AppSync)
                additional_authorization_modes=[
                    appsync.AuthorizationMode(
                        authorization_type=appsync.AuthorizationType.IAM,
                    )
                ],
            ),
            # Configure logging for troubleshooting
            log_config=appsync.LogConfig(
                retention=logs.RetentionDays.ONE_WEEK,
                field_log_level=appsync.FieldLogLevel.ALL,
            ),
        )

        # Create DynamoDB table for session tracking (optional)
        #
        # DynamoDB Table:
        # - Serverless NoSQL database for storing session state information
        # - Uses sessionId as the partition key for efficient lookups
        # - Pay-per-request billing model to handle variable workloads
        # - Table will be automatically deleted when stack is destroyed
        sessions_table = dynamodb.Table(
            self,
            "SessionsTable",
            table_name="streaming-sessions",
            partition_key=dynamodb.Attribute(
                name="sessionId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=True,
        )

        # Create DLQ with SSL enforcement
        streaming_dlq = sqs.Queue(
            self,
            "StreamingDLQ",
            retention_period=Duration.days(
                14
            ),  # Keep failed messages for 2 weeks for analysis
            # Fixed: Enforce SSL for SQS (SQS4)
            enforce_ssl=True,
        )

        # Create an SQS queue for processing LLM stream requests
        #
        # Message Queue Architecture:
        # Unlike direct Lambda-to-Lambda invocation (anti-pattern), using SQS:
        # 1. Decouples components - Request and Processing functions operate independently
        # 2. Provides automatic retries - Failed messages are retried according to queue settings
        # 3. Enables resilience - Dead-letter queue captures failures for troubleshooting
        # 4. Improves scaling - Can buffer requests during traffic spikes
        streaming_queue = sqs.Queue(
            self,
            "StreamingQueue",
            # Visibility timeout must be greater than Lambda timeout to prevent duplicate processing
            visibility_timeout=Duration.minutes(16),
            # Message retention defines how long messages stay in queue if not processed
            retention_period=Duration.hours(1),
            enforce_ssl=True,
            # Dead-letter queue for capturing failed processing attempts
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,  # After 3 failed attempts, send to DLQ
                queue=streaming_dlq,
            ),
        )

        # 2. Processing Lambda: The long-running function that calls Bedrock
        #
        # SQS-Triggered Processing Lambda:
        # - Receives messages from SQS queue rather than direct invocation
        # - Handles the long-running LLM stream processing (up to 15 minutes)
        # - Communicates back to clients through AppSync subscriptions
        # - Higher memory allocation for faster processing of LLM responses
        processing_function = _lambda.Function(
            self,
            "StreamingProcessingFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="processing.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/appsync"),
            timeout=Duration.minutes(15),  # Long timeout for streaming responses
            memory_size=1024,  # Higher memory allocation for performance
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "APPSYNC_API_URL": api.graphql_url,  # Used for publishing tokens
                "SESSIONS_TABLE": sessions_table.table_name,  # For session management
            },
        )

        # Add SQS as an event source for the processing Lambda
        #
        # Event Source Pattern:
        # - Lambda is triggered automatically when messages arrive in SQS
        # - Batch size of 1 ensures one LLM request is processed at a time
        # - Zero batching window means messages are processed immediately
        # - Report batch failures enables partial batch success handling
        processing_function.add_event_source(
            lambda_event_sources.SqsEventSource(
                streaming_queue,
                batch_size=1,  # Process one message at a time
                max_batching_window=Duration.seconds(0),  # Process immediately
                report_batch_item_failures=True,  # Enable partial batch failures
            )
        )

        # Grant processing Lambda permission to invoke Bedrock
        #
        # IAM Permissions:
        # - Allows the Lambda to invoke Bedrock streaming APIs
        # - Uses streaming variant of the API for real-time token delivery
        processing_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModelWithResponseStream"],
                resources=["*"],
            )
        )

        # Grant processing Lambda permission to publish back to AppSync
        #
        # Service-to-Service Authentication:
        # - Lambda needs to authenticate to AppSync using IAM
        # - Restricted to just the publishToken mutation for security
        # - Uses the GraphQL endpoint to send real-time updates
        processing_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["appsync:GraphQL"],
                resources=[f"{api.arn}/types/Mutation/fields/publishToken"],
            )
        )

        # 1. Request Lambda: The short-lived function linked to the AppSync resolver
        #
        # Fast-Response Request Pattern:
        # - Short-lived function (30-second timeout) for quick response to client
        # - Handles initial request validation and session creation
        # - Delegates actual processing to SQS/Processing Lambda
        # - Uses minimal memory as it only performs lightweight operations
        request_function = _lambda.Function(
            self,
            "StreamingRequestFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="request.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/appsync"),
            timeout=Duration.seconds(30),  # Short timeout as it returns quickly
            memory_size=256,  # Lower memory as it's not doing intensive work
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "STREAMING_QUEUE_URL": streaming_queue.queue_url,  # Used for sending messages to queue
            },
        )

        # Grant request Lambda permission to send messages to SQS
        #
        # Request-to-Queue Pattern:
        # - Request Lambda needs permission to put messages into SQS
        # - This replaces direct Lambda-to-Lambda invocation
        # - More loosely coupled design for better error handling and scalability
        streaming_queue.grant_send_messages(request_function)

        # Grant processing Lambda permission to read/write to DynamoDB
        #
        # Session State Management:
        # - Processing Lambda needs to read/write session data
        # - Useful for tracking streaming progress and state
        # - Enables resumability and analytics capabilities
        sessions_table.grant_read_write_data(processing_function)

        # Create Lambda data source for the AppSync 'startStream' mutation
        #
        # AppSync Data Source:
        # - Links the GraphQL API to the request Lambda function
        # - When the startStream mutation is called, this Lambda is invoked
        # - Provides the integration between client GraphQL operations and backend processing
        lambda_data_source = api.add_lambda_data_source(
            "StreamingDataSource",
            request_function,  # Link the request function to the resolver
            name="StreamingDataSource",
            description="Lambda data source for starting the Bedrock stream",
        )

        # Create NONE data source for publishToken mutation
        #
        # NONE Data Source:
        # - Special AppSync data source that doesn't connect to a backend
        # - Used for the publishToken mutation which is called by the processing Lambda
        # - AppSync handles the direct mapping between request and response
        # - Enables server-to-server communication (Processing Lambda → AppSync)
        none_data_source = api.add_none_data_source(
            "NoneDataSource",
            name="NoneDataSource",
            description="None data source for direct Lambda calls",
        )

        # Resolver for startStream mutation
        #
        # Client-Facing Resolver Pattern:
        # - Handles the initial client mutation to start streaming
        # - Maps directly to the request Lambda data source
        # - Uses default mapping templates to pass all arguments to Lambda
        # - Returns the Lambda's response back to the client (sessionId, etc.)
        api.create_resolver(
            "StartStreamResolver",
            type_name="Mutation",
            field_name="startStream",
            data_source=lambda_data_source,
            request_mapping_template=appsync.MappingTemplate.lambda_request(),
            response_mapping_template=appsync.MappingTemplate.lambda_result(),
        )

        # Resolver for publishToken mutation
        #
        # Server-to-Server Resolver Pattern:
        # - This mutation is not called by clients, but by the processing Lambda
        # - Uses the NONE data source with custom VTL mapping templates
        # - When processing Lambda calls this mutation, it triggers subscriptions
        # - Clients listening via subscription will receive these tokens in real-time
        # - The key to implementing real-time streaming to multiple clients
        api.create_resolver(
            "PublishTokenResolver",
            type_name="Mutation",
            field_name="publishToken",
            data_source=none_data_source,
            request_mapping_template=appsync.MappingTemplate.from_string(
                """
            {
                "version": "2018-05-29",
                "payload": {
                    "sessionId": $util.toJson($ctx.args.sessionId),
                    "token": $util.toJson($ctx.args.token),
                    "isComplete": $util.toJson($ctx.args.isComplete),
                    "timestamp": $util.toJson($util.time.nowISO8601())
                }
            }
            """
            ),
            response_mapping_template=appsync.MappingTemplate.from_string(
                """
            {
                "sessionId": $util.toJson($ctx.args.sessionId),
                "token": $util.toJson($ctx.args.token),
                "isComplete": $util.toJson($ctx.args.isComplete),
                "timestamp": $util.toJson($util.time.nowISO8601())
            }
            """
            ),
        )

        # Output values for cross-stack references
        #
        # Exposing Resources:
        # - Makes these resources available to other stacks if needed
        # - Enables modular architecture with cross-stack references
        # - Useful for larger applications with multiple deployment stacks
        self.api = api
        self.request_function = request_function
        self.processing_function = processing_function
        self.sessions_table = sessions_table
        self.streaming_queue = streaming_queue
        self.user_pool = user_pool
        self.user_pool_client = user_pool_client

        # Add stack outputs for CLI and console visibility
        #
        # CloudFormation Outputs:
        # - Display key information in the AWS Console after deployment
        # - Available through AWS CLI with 'aws cloudformation describe-stacks'
        # - Used by frontend applications to discover backend endpoints
        # - Simplify the integration between frontend and backend components
        from aws_cdk import CfnOutput

        CfnOutput(
            self,
            "AppSyncAPIURL",
            value=api.graphql_url,
            description="AppSync GraphQL API URL for client connections",
        )

        CfnOutput(
            self,
            "StreamingQueueURL",
            value=streaming_queue.queue_url,
            description="SQS Queue URL for streaming requests",
        )

        CfnOutput(
            self,
            "AppSyncAPIID",
            value=api.api_id,
            description="AppSync API ID for configuration reference",
        )

        CfnOutput(
            self,
            "RequestFunctionName",
            value=request_function.function_name,
            description="Lambda function name for request handling",
        )

        CfnOutput(
            self,
            "ProcessingFunctionName",
            value=processing_function.function_name,
            description="Lambda function name for LLM processing",
        )

        CfnOutput(
            self,
            "UserPoolId",
            value=user_pool.user_pool_id,
            description="Cognito User Pool ID for authentication",
        )

        CfnOutput(
            self,
            "UserPoolClientId",
            value=user_pool_client.user_pool_client_id,
            description="Cognito User Pool Client ID for frontend apps",
        )

        # Add CDK-Nag suppressions for acceptable findings
        NagSuppressions.add_resource_suppressions(
            processing_function.role,
            [
                {
                    "id": "AwsSolutions-IAM4",
                    "reason": "AWSLambdaBasicExecutionRole is the standard managed policy for Lambda execution roles and provides necessary CloudWatch Logs permissions",
                },
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard permissions are required for Bedrock model access (dynamic ARNs) and Lambda-generated resources like DynamoDB and CloudWatch Logs",
                },
            ],
        )

        NagSuppressions.add_resource_suppressions(
            request_function.role,
            [
                {
                    "id": "AwsSolutions-IAM4",
                    "reason": "AWSLambdaBasicExecutionRole is the standard managed policy for Lambda execution roles and provides necessary CloudWatch Logs permissions",
                },
            ],
        )

        # Suppress AppSync API logs role managed policy usage
        NagSuppressions.add_resource_suppressions(
            api.node.find_child("ApiLogsRole"),
            [
                {
                    "id": "AwsSolutions-IAM4",
                    "reason": "AWSAppSyncPushToCloudWatchLogs is the standard managed policy for AppSync logging and is required for CloudWatch integration",
                }
            ],
        )

        # Suppress lambda data source service role wildcard permissions
        NagSuppressions.add_resource_suppressions(
            lambda_data_source.node.find_child("ServiceRole").node.find_child(
                "DefaultPolicy"
            ),
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "AppSync Lambda data source requires wildcard permissions to invoke the associated Lambda function with dynamic ARN suffixes",
                }
            ],
        )

        # Suppress processing function default policy wildcard permissions
        NagSuppressions.add_resource_suppressions(
            processing_function.role.node.find_child("DefaultPolicy"),
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Processing Lambda requires wildcard permissions for Bedrock access, DynamoDB operations, and SQS message processing with dynamic resource ARNs",
                }
            ],
        )

        # Suppress Lambda runtime findings for Python functions
        for func in [processing_function, request_function]:
            NagSuppressions.add_resource_suppressions(
                func,
                [
                    {
                        "id": "AwsSolutions-L1",
                        "reason": "Python 3.12 is the latest stable Python runtime available in AWS Lambda. Using the current stable version for reliability.",
                    }
                ],
            )

        # Suppress CDK auto-generated log retention function findings
        NagSuppressions.add_stack_suppressions(
            self,
            [
                {
                    "id": "AwsSolutions-IAM4",
                    "reason": "CDK auto-generated log retention functions use standard Lambda execution roles required for CloudWatch Logs operations",
                    "applies_to": [
                        "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
                    ],
                },
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "CDK auto-generated log retention functions require wildcard permissions for CloudWatch Logs operations across multiple log groups",
                    "applies_to": ["Resource::*"],
                },
            ],
        )
