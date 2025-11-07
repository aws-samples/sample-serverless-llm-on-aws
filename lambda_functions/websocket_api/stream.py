"""
WebSocket API AI Streaming Handler

This function handles the core AI streaming functionality by integrating WebSocket
communication with AWS Bedrock. It demonstrates real-time AI response streaming
through persistent WebSocket connections.

Key Concepts Demonstrated:
1. WebSocket Bidirectional Communication - Client sends request, server streams response
2. AWS Bedrock Integration - Invoking Claude AI model with streaming
3. Real-time Data Streaming - Forwarding AI tokens as they're generated
4. Connection Management - Handling connection failures gracefully
5. Error Handling - Managing AI service errors and connection issues

WebSocket Message Flow:
Client → {"action": "stream", "prompt": "Hello, how are you?"}
         ↓
      Lambda processes request
         ↓
      Bedrock streams AI response
         ↓
      Tokens forwarded to client in real-time
         ↓
      {"type": "token", "token": "Hello"}
      {"type": "token", "token": "! I'm"}
      {"type": "token", "token": " doing"}
      {"type": "complete"}

Architecture Benefits:
- Real-time Response: Users see AI responses as they're generated
- Scalable: WebSocket connections handle multiple concurrent users
- Resilient: Graceful handling of connection drops and AI service errors
- Efficient: No polling required, true push-based communication
"""

import json
import boto3
from botocore.exceptions import ClientError


def lambda_handler(event, context):
    """
    Handle AI Streaming Requests via WebSocket

    This function is invoked when clients send messages to the "stream" route.
    It processes the user's prompt, streams the AI response back through the
    WebSocket connection in real-time.

    Event Structure:
    {
        "requestContext": {
            "connectionId": "L0SM9cOFvHcCIhw=",    # WebSocket connection ID
            "eventType": "MESSAGE",                # Message event
            "stage": "prod",                       # API stage
            "domainName": "api-id.execute-api.region.amazonaws.com",
            "identity": {
                "principalId": "user-sub-from-cognito"  # From authorization
            }
        },
        "body": '{"action": "stream", "prompt": "What is AWS Lambda?"}',
        "isBase64Encoded": false
    }

    Client Message Format:
    {
        "action": "stream",                    # Route to this handler
        "prompt": "What is AWS Lambda?",       # User's question/prompt
        "options": {                           # Optional configuration
            "max_tokens": 1000,
            "temperature": 0.7
        }
    }

    Response Messages Sent to Client:
    {"type": "token", "token": "AWS Lambda"}   # Each AI token as generated
    {"type": "complete"}                       # Indicates streaming is finished
    {"type": "error", "message": "..."}       # Error notifications
    """

    # Extract WebSocket connection information
    connection_id = event["requestContext"]["connectionId"]
    domain_name = event["requestContext"]["domainName"]
    stage = event["requestContext"]["stage"]

    # Get user identity for logging and potential personalization
    principal_id = event["requestContext"].get("identity", {}).get("principalId")

    # Parse the incoming message from the client
    try:
        body = json.loads(event.get("body", "{}"))
        prompt = body.get("prompt", "Hello, how are you?")
        max_tokens = body.get("options", {}).get("max_tokens", 1000)

        print(f"Processing AI streaming request:")
        print(f"  User: {principal_id}")
        print(f"  Connection: {connection_id}")
        print(f"  Prompt: {prompt[:100]}...")  # Log first 100 chars for privacy
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in request body: {e}")
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON"})}

    # Create API Gateway Management API client for WebSocket communication
    # This client allows us to send messages back to the connected WebSocket client
    apigateway_management_api = boto3.client(
        "apigatewaymanagementapi", endpoint_url=f"https://{domain_name}/{stage}"
    )

    # Create Bedrock Runtime client for AI model invocation
    # This client handles communication with AWS Bedrock AI services
    bedrock_runtime = boto3.client("bedrock-runtime")

    try:
        # Invoke Claude 3.5 Sonnet with response streaming
        # This enables real-time token streaming as the AI generates the response
        print(f"Invoking Bedrock model for user {principal_id}")
        response = bedrock_runtime.invoke_model_with_response_stream(
            modelId="anthropic.claude-3-5-sonnet-20240620-v1:0",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                    # Optional: Add system prompts, temperature, etc.
                    # "system": "You are a helpful AI assistant specialized in AWS services.",
                    # "temperature": 0.7,
                    # "top_p": 0.9
                }
            ),
            contentType="application/json",
            accept="application/json",
        )

        # Process streaming response from Bedrock
        # The response comes as chunks containing different types of data
        token_count = 0
        for chunk in response["body"]:
            if "chunk" in chunk:
                # Decode the binary chunk data to JSON
                chunk_data = json.loads(chunk["chunk"]["bytes"].decode("utf-8"))

                # Filter for content generation chunks (actual AI text)
                if chunk_data.get("type") == "content_block_delta":
                    text = chunk_data.get("delta", {}).get("text", "")
                    if text:
                        token_count += 1
                        try:
                            # Send the AI token immediately to the WebSocket client
                            # This enables real-time streaming as the AI generates text
                            apigateway_management_api.post_to_connection(
                                ConnectionId=connection_id,
                                Data=json.dumps(
                                    {
                                        "type": "token",
                                        "token": text,
                                        "sequence": token_count,  # Optional: for ordering
                                    }
                                ),
                            )
                        except ClientError as e:
                            # Handle connection closure scenarios
                            if e.response["Error"]["Code"] == "GoneException":
                                print(
                                    f"Connection {connection_id} closed during streaming"
                                )
                                print(f"  User: {principal_id}")
                                print(f"  Tokens sent: {token_count}")
                                break
                            else:
                                # Re-raise other API Gateway errors
                                raise e

        # Send completion notification to indicate streaming is finished
        try:
            apigateway_management_api.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps(
                    {
                        "type": "complete",
                        "total_tokens": token_count,
                        "timestamp": context.aws_request_id,
                    }
                ),
            )
            print(
                f"Streaming completed successfully for {principal_id}: {token_count} tokens"
            )
        except ClientError as e:
            # Don't fail if we can't send completion (connection might be closed)
            if e.response["Error"]["Code"] != "GoneException":
                raise e

    except Exception as e:
        # Handle any errors during AI processing or WebSocket communication
        error_message = str(e)
        print(f"Streaming error for user {principal_id}: {error_message}")

        try:
            # Attempt to notify the client about the error
            apigateway_management_api.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps(
                    {
                        "type": "error",
                        "message": error_message,
                        "timestamp": context.aws_request_id,
                    }
                ),
            )
        except:
            # If we can't send error notification, just log it
            print(f"Could not send error notification to connection {connection_id}")

    # Return success response to API Gateway
    # The actual response to the client is sent via WebSocket messages above
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "AI streaming request processed",
                "requestId": context.aws_request_id,
            }
        ),
    }
