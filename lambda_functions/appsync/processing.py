"""
AWS AppSync LLM Streaming Processing Lambda Function

This function demonstrates advanced serverless patterns for real-time LLM streaming using
AWS AppSync GraphQL subscriptions. It showcases several key architectural concepts:

Key Concepts Demonstrated:
1. Message-Based Processing - Triggered by SQS events for better decoupling
2. GraphQL Mutations - Programmatic execution of GraphQL operations from Lambda
3. SigV4 Authentication - Service-to-service authentication using IAM roles
4. Real-time Subscriptions - Publishing data to GraphQL subscribers in real-time
5. Bedrock Integration - Streaming LLM responses from Claude models
6. Error Handling - Graceful failure management in distributed systems

Architecture Pattern:
Client → AppSync startStream mutation → Request Lambda → SQS Queue → Processing Lambda (this function)
    ↓
Processing Lambda → Bedrock LLM streaming → GraphQL publishToken mutations → AppSync subscriptions
    ↓
AppSync → Real-time updates to subscribed clients

This pattern enables:
- Non-blocking user experience (immediate response)
- Real-time streaming without persistent connections
- Scalable architecture using serverless components
- GraphQL-native real-time capabilities
- Enhanced resilience with SQS retries and dead-letter queues
"""

import json
import boto3
import os
from botocore.exceptions import ClientError


def publish_token_to_appsync(
    session_id, token, is_complete, sequence, appsync_url, region
):
    """
    Publish LLM tokens to AppSync using GraphQL mutations with IAM authentication

    This function demonstrates how to programmatically execute GraphQL mutations
    from within a Lambda function using AWS SigV4 authentication. This pattern
    enables service-to-service communication in a secure, scalable way.

    Key Concepts:
    - GraphQL Mutations: Programmatic execution of schema operations
    - SigV4 Authentication: AWS signature-based authentication for APIs
    - Real-time Publishing: Triggering AppSync subscriptions from Lambda
    - Error Handling: Graceful failure management for GraphQL operations

    Authentication Flow:
    1. Lambda retrieves IAM credentials from execution role
    2. SigV4Auth signs the GraphQL request with temporary credentials
    3. AppSync validates the signature and executes the mutation
    4. Mutation triggers subscriptions to connected clients

    Args:
        session_id (str): Unique identifier for the streaming session
        token (str): LLM-generated text token to publish
        is_complete (bool): Whether this is the final token in the stream
        sequence (int): Token sequence number for ordering
        appsync_url (str): GraphQL endpoint URL for AppSync API
        region (str): AWS region for SigV4 signing

    Returns:
        bool: True if publication successful, False otherwise

    GraphQL Mutation Schema:
    mutation PublishToken($sessionId: String!, $token: String!, $isComplete: Boolean!) {
        publishToken(sessionId: $sessionId, token: $token, isComplete: $isComplete) {
            sessionId
            token
            isComplete
            timestamp
        }
    }
    """
    try:
        # Import AWS authentication libraries for SigV4 signing
        # These libraries enable secure service-to-service communication
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest
        import urllib.request

        # GraphQL Mutation Definition
        # This mutation matches the schema defined in AppSync and triggers
        # real-time subscriptions to connected clients
        mutation = """
        mutation PublishToken($sessionId: String!, $token: String!, $isComplete: Boolean!) {
            publishToken(sessionId: $sessionId, token: $token, isComplete: $isComplete) {
                sessionId
                token
                isComplete
                timestamp
            }
        }
        """

        # Prepare GraphQL request payload
        # Standard GraphQL request format with query and variables
        variables = {"sessionId": session_id, "token": token, "isComplete": is_complete}
        payload = {"query": mutation, "variables": variables}
        json_data = json.dumps(payload).encode("utf-8")

        # AWS Authentication Setup
        # Retrieve credentials from Lambda execution role for SigV4 signing
        session = boto3.Session()
        credentials = session.get_credentials()

        # Create AWS request object for SigV4 authentication
        # This ensures the request is properly signed with IAM credentials
        request = AWSRequest(
            method="POST",
            url=appsync_url,
            data=json_data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )

        # Apply SigV4 authentication signature
        # This signs the request using the Lambda's IAM role credentials
        # AppSync will validate this signature before executing the mutation
        SigV4Auth(credentials, "appsync", region).add_auth(request)

        # Execute the signed GraphQL request
        # Convert botocore request to urllib request and send to AppSync
        req = urllib.request.Request(
            appsync_url, data=json_data, headers=dict(request.headers)
        )

        # Send request and handle response
        # 30-second timeout prevents hanging on slow AppSync responses
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

            # Check for GraphQL errors in the response
            # Even successful HTTP requests can contain GraphQL errors
            if "errors" in result:
                print(f"❌ GraphQL errors: {result['errors']}")
                return False

        print(f"✅ Successfully published token to AppSync for session {session_id}")
        return True

    except Exception as e:
        # Handle any errors during GraphQL publication
        # Common errors: network issues, authentication failures, schema mismatches
        print(f"❌ Error publishing token to AppSync: {str(e)}")
        return False


def process_streaming_request(message_body):
    """
    Process a single LLM streaming request from an SQS message

    This function handles the core business logic of invoking Bedrock and
    streaming the results back to AppSync subscribers. It's extracted into
    a separate function to facilitate batch processing of SQS messages.

    Args:
        message_body (dict): The parsed JSON body of the SQS message

    Returns:
        bool: True if processing was successful, False otherwise
    """
    prompt = message_body["prompt"]
    session_id = message_body["sessionId"]

    # Get configuration from environment variables
    # These are set by CDK during deployment
    appsync_api_url = os.environ["APPSYNC_API_URL"]
    region = os.environ["AWS_REGION"]

    print(f"🚀 PROCESSOR: Starting Bedrock stream for session: {session_id}")
    print(f"📝 PROCESSOR: Prompt preview: '{prompt[:100]}...'")  # Truncate for privacy

    try:
        # Initialize Bedrock Runtime client for LLM model invocation
        bedrock_runtime = boto3.client("bedrock-runtime")

        # Invoke Claude 3.5 Sonnet with streaming response
        # This enables real-time token generation as the LLM formulates its response
        print(f"🤖 PROCESSOR: Invoking Claude 3.5 Sonnet model...")
        response = bedrock_runtime.invoke_model_with_response_stream(
            modelId="anthropic.claude-3-5-sonnet-20240620-v1:0",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": prompt}],
                    # Optional: Add system prompts, temperature, etc.
                    # "system": "You are a helpful AI assistant...",
                    # "temperature": 0.7,
                    # "top_p": 0.9
                }
            ),
            contentType="application/json",
            accept="application/json",
        )

        # Process streaming response from Bedrock
        # Each chunk contains different types of data; we filter for text content
        token_count = 0
        print(f"📡 PROCESSOR: Beginning real-time token streaming...")

        for chunk in response["body"]:
            if "chunk" in chunk:
                # Decode the binary chunk data to JSON
                chunk_data = json.loads(chunk["chunk"]["bytes"].decode("utf-8"))

                # Filter for actual text content chunks
                if chunk_data.get("type") == "content_block_delta":
                    text = chunk_data.get("delta", {}).get("text", "")
                    if text:
                        token_count += 1

                        # Publish each token immediately to AppSync
                        # This triggers real-time subscriptions to connected clients
                        success = publish_token_to_appsync(
                            session_id=session_id,
                            token=text,
                            is_complete=False,
                            sequence=token_count,
                            appsync_url=appsync_api_url,
                            region=region,
                        )

                        # Log progress for monitoring (could add metrics here)
                        if token_count % 10 == 0:  # Log every 10 tokens
                            print(f"📊 PROCESSOR: Published {token_count} tokens...")

        # Send completion notification to indicate streaming is finished
        print(
            f"✅ PROCESSOR: Stream completed successfully. Total tokens: {token_count}"
        )
        publish_token_to_appsync(
            session_id=session_id,
            token="",  # Empty token indicates completion
            is_complete=True,
            sequence=token_count + 1,
            appsync_url=appsync_api_url,
            region=region,
        )

        return True

    except Exception as e:
        # Handle any errors during AI processing or publication
        error_message = str(e)
        print(f"❌ PROCESSOR: Error during streaming: {error_message}")

        # Notify clients of the error through AppSync
        # This ensures users get feedback even when things go wrong
        publish_token_to_appsync(
            session_id=session_id,
            token=f"Error: {error_message}",
            is_complete=True,
            sequence=999,  # High sequence number for error messages
            appsync_url=appsync_api_url,
            region=region,
        )

        return False


def lambda_handler(event, context):
    """
    AppSync LLM Streaming Processing Lambda Handler

    This function is triggered by SQS events containing LLM streaming requests.
    It demonstrates a message-based approach to handling long-running operations:

    Message-Based Processing Pattern:
    - Triggered by SQS events rather than direct Lambda invocation
    - Provides automatic retries and dead-letter queue capabilities
    - Allows for graceful failure handling and improved resilience
    - Enables horizontal scaling through SQS's distributed nature

    Real-time Publishing Pattern:
    - Streams LLM responses in real-time as they're generated
    - Uses GraphQL mutations to trigger AppSync subscriptions
    - Provides immediate feedback to users without polling
    - Maintains session continuity across the streaming process

    SQS Event Structure:
    {
        "Records": [
            {
                "messageId": "unique-message-id",
                "receiptHandle": "handle-for-deletion",
                "body": "JSON string containing prompt and sessionId",
                "attributes": {...},
                "messageAttributes": {...},
                ...
            },
            ...
        ]
    }

    Environment Variables Required:
    - APPSYNC_API_URL: GraphQL endpoint for publishing tokens
    - AWS_REGION: AWS region for service calls

    Returns:
        dict: Batch item failures if any messages couldn't be processed

    Architecture Benefits:
    - Decoupling: No direct dependencies between components
    - Resilience: Automatic retries for failed processing
    - Observability: Clear separation of concerns for easier debugging
    - Scalability: SQS handles the load distribution automatically
    """
    print(f"📥 Received SQS event with {len(event.get('Records', []))} messages")

    # Initialize tracking for failed messages
    failed_message_ids = []

    # Process each message in the batch
    for record in event.get("Records", []):
        message_id = record["messageId"]
        print(f"⚙️ Processing message {message_id}")

        try:
            # Parse the message body (which is a JSON string)
            message_body = json.loads(record["body"])

            # Process this specific streaming request
            success = process_streaming_request(message_body)

            if not success:
                # Mark message for retry by including it in failed list
                failed_message_ids.append({"itemIdentifier": message_id})
                print(f"❌ Failed to process message {message_id}, will be retried")

        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse message {message_id}: Invalid JSON: {str(e)}")
            # Don't retry messages with invalid JSON - they'll never succeed

        except Exception as e:
            # For any other exceptions, mark the message for retry
            print(f"⚠️ Unexpected error processing message {message_id}: {str(e)}")
            failed_message_ids.append({"itemIdentifier": message_id})

    # Return information about any failed messages that should be retried
    # SQS will retry these messages according to the queue configuration
    return {"batchItemFailures": failed_message_ids}
